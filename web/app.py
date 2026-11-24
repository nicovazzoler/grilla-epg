"""La web de grilla-epg: subir grillas, revisar los nombres nuevos y bajar el EPG.
Uso local: uvicorn web.app:app --port 8011   (desde la raíz del repo)"""
import asyncio
from contextlib import asynccontextmanager
import datetime as dt
import importlib
import json
import re
import tempfile
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from procesar import Frenado, MINUTOS_A_MANO, limpiar_reparto, reparto, senales
from web import corridas
from web.base import preparar, sesion_db
from web.modelos import Corrida, Entrada, Pendiente
from web.sesion import COOKIE, DURACION, credenciales_configuradas, credenciales_validas, crear_token, usuario_actual

ESTATICOS = Path(__file__).parent / 'static'
# Lo que tarda una grilla con la herramienta, revisión incluida: con esto se estima lo ahorrado.
MINUTOS_CON_LA_HERRAMIENTA = 3



@asynccontextmanager
async def al_arrancar(_):
    preparar(senales())
    yield


app = FastAPI(title='grilla-epg', docs_url=None, redoc_url=None, lifespan=al_arrancar)
app.mount('/static', StaticFiles(directory=ESTATICOS), name='static')


@app.middleware('http')
async def sin_cache(request: Request, call_next):
    # Sin esto el navegador sigue usando el JS de antes de un deploy.
    respuesta = await call_next(request)
    if request.url.path == '/' or request.url.path.startswith('/static/'):
        respuesta.headers['Cache-Control'] = 'no-cache'
    return respuesta


def lector(senal):
    if senal not in senales():
        raise HTTPException(404, f'No hay lector para la señal {senal!r}.')
    return importlib.import_module(f'senales.{senal}')


def la_corrida(db, corrida_id):
    if not (corrida := db.get(Corrida, corrida_id)):
        raise HTTPException(404, 'Esa corrida no existe o ya se borró (se guardan 30 días).')
    return corrida


@app.get('/')
def inicio():
    return FileResponse(ESTATICOS / 'index.html')


@app.post('/api/login')
async def login(request: Request):
    datos = await request.json()
    if not credenciales_configuradas():
        raise HTTPException(503, 'Faltan APP_USUARIO y APP_CLAVE en las variables del servidor.')
    if not credenciales_validas(str(datos.get('usuario', '')), str(datos.get('clave', ''))):
        await asyncio.sleep(1)
        raise HTTPException(401, 'Usuario o clave incorrectos.')
    respuesta = JSONResponse({'usuario': datos['usuario']})
    https = request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'
    respuesta.set_cookie(COOKIE, crear_token(datos['usuario']), max_age=DURACION, httponly=True, samesite='lax',
                         secure=https)
    return respuesta


@app.post('/api/salir')
def salir():
    respuesta = JSONResponse({'ok': True})
    respuesta.delete_cookie(COOKIE)
    return respuesta


@app.get('/api/yo')
def yo(usuario=Depends(usuario_actual)):
    return {'usuario': usuario}


@app.get('/api/senales')
def lista_de_senales(_=Depends(usuario_actual)):
    return [{'id': s, 'nombre': lector(s).NOMBRE, 'corrige_horas': getattr(lector(s), 'CORRIGE_HORAS', False)}
            for s in senales()]


@app.post('/api/corridas')
async def nueva_corrida(archivos: list[UploadFile] = File(...), senal: str = Form(''), semanal: bool = Form(False),
                        horas: str = Form('{}'), db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    nombres = [Path(a.filename or 'grilla').name for a in archivos]
    senal = senal or corridas.detectar_senal(nombres)
    if not senal:
        return JSONResponse({'pregunta': 'senal', 'mensaje': 'No reconozco la señal por el nombre del archivo: ¿cuál es?'},
                            status_code=422)
    lector(senal)
    try:
        horas_corregidas = {int(f): dt.datetime.strptime(h, '%H:%M').time() for f, h in json.loads(horas).items()}
    except (ValueError, AttributeError):
        raise HTTPException(422, 'Las horas corregidas van como HH:MM.')

    # Las grillas no se guardan: se leen desde una carpeta temporal que se borra al terminar.
    with tempfile.TemporaryDirectory() as carpeta:
        rutas = []
        for i, (archivo, nombre) in enumerate(zip(archivos, nombres)):
            ruta = Path(carpeta) / f'{i:02d}_{re.sub(r"[^\w.\-]", "_", nombre)}'
            ruta.write_bytes(await archivo.read())
            rutas.append(str(ruta))
        try:
            corrida = await asyncio.to_thread(corridas.crear, db, senal, rutas, nombres, horas_corregidas, semanal)
        except Frenado as e:
            filas = [{'fila': int(m.group(1)) if (m := re.fullmatch(r'fila (\d+)', f['ref'])) else None,
                      'ref': f['ref'], 'hora': f'{f["inicio"]:%H:%M}', 'dia': f'{f["inicio"]:%d/%m}', 'nombre': f['nombre']}
                     for f in e.filas]
            return JSONResponse({'frenado': str(e), 'filas': filas, 'senal': senal,
                                 'corrige_horas': getattr(lector(senal), 'CORRIGE_HORAS', False)}, status_code=409)
        except SystemExit as e:
            raise HTTPException(422, f'El lector de {senal} no pudo con la grilla: {e}')
        except Exception as e:
            detalle = re.sub(r"'?/\S+/\d\d_([^'\s]+)'?", r'\1', str(e))
            raise HTTPException(422, f'El lector de {lector(senal).NOMBRE} no pudo leer la grilla ({detalle}). '
                                     '¿Es de esa señal?')
    return {'id': corrida.id}


@app.get('/api/corridas')
def lista_de_corridas(db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    faltan = dict(db.execute(select(Pendiente.corrida_id, func.count()).where(Pendiente.estado != 'aprobado')
                             .group_by(Pendiente.corrida_id)).all())
    return [{'id': c.id, 'senal': c.senal, 'creada': c.creada.isoformat(timespec='minutes'), 'archivos': c.archivos,
             'capas': c.capas, 'semanal': c.semanal, 'faltan': faltan.get(c.id, 0)}
            for c in db.scalars(select(Corrida).order_by(Corrida.creada.desc()))]


@app.get('/api/corridas/{corrida_id}')
def ver_corrida(corrida_id: int, db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    return corridas.vista(db, la_corrida(db, corrida_id))


@app.get('/api/corridas/{corrida_id}/excel')
def bajar_excel(corrida_id: int, db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    nombre, contenido = corridas.excel(db, la_corrida(db, corrida_id))
    return Response(contenido, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{nombre}"'})


@app.post('/api/corridas/{corrida_id}/aprobar-parecidos')
def aprobar_parecidos(corrida_id: int, db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    corrida = la_corrida(db, corrida_id)
    aprobados = 0
    for p in [p for p in corrida.pendientes if p.capa == 'parecido' and p.estado != 'aprobado']:
        if corridas.aprobar(db, p, p.propuesta):
            aprobados += 1
    return {'aprobados': aprobados}


@app.post('/api/pendientes/{pendiente_id}/aprobar')
async def aprobar_pendiente(pendiente_id: int, request: Request, db: Session = Depends(sesion_db),
                            _=Depends(usuario_actual)):
    if not (pendiente := db.get(Pendiente, pendiente_id)):
        raise HTTPException(404, 'Ese pendiente no existe.')
    propuesta = (await request.json()).get('reparto') or {}
    editado = limpiar_reparto(propuesta) != limpiar_reparto(pendiente.propuesta)
    if not (r := corridas.aprobar(db, pendiente, propuesta, 'a mano' if editado else None)):
        raise HTTPException(422, 'Falta el título.')
    return {'reparto': r}


@app.post('/api/pendientes/{pendiente_id}/saltear')
def saltear_pendiente(pendiente_id: int, db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    if not (pendiente := db.get(Pendiente, pendiente_id)):
        raise HTTPException(404, 'Ese pendiente no existe.')
    pendiente.estado = 'salteado'
    db.commit()
    return {'ok': True}


@app.get('/api/diccionario/{senal}')
def ver_diccionario(senal: str, q: str = '', db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    lector(senal)
    consulta = select(Entrada).where(Entrada.senal == senal).order_by(Entrada.aprobada.desc(), Entrada.crudo)
    entradas = list(db.scalars(consulta))
    if q:
        q = q.lower()
        entradas = [e for e in entradas if q in e.crudo.lower() or q in json.dumps(e.reparto, ensure_ascii=False).lower()]
    total = len(entradas)
    return {'total': total, 'entradas': [{'id': e.id, 'crudo': e.crudo, 'reparto': reparto(e.reparto), 'capa': e.capa,
                                          'aprobada': e.aprobada.isoformat(timespec='minutes')} for e in entradas[:300]]}


@app.put('/api/diccionario/{senal}/{entrada_id}')
async def editar_entrada(senal: str, entrada_id: int, request: Request, db: Session = Depends(sesion_db),
                         _=Depends(usuario_actual)):
    entrada = db.get(Entrada, entrada_id)
    if not entrada or entrada.senal != senal:
        raise HTTPException(404, 'Esa entrada no existe.')
    r = limpiar_reparto((await request.json()).get('reparto') or {})
    if not r['TIT PRINC']:
        raise HTTPException(422, 'Falta el título.')
    entrada.reparto, entrada.capa, entrada.aprobada = r, 'a mano', dt.datetime.now()
    db.commit()
    return {'reparto': r}


@app.get('/api/diccionario/{senal}/exportar')
def exportar_diccionario(senal: str, db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    lector(senal)
    # Mismo formato que diccionario/<señal>.json del repo: solo el título se guarda como texto.
    salida = {e.crudo: (e.reparto['TIT PRINC'] if list(e.reparto) == ['TIT PRINC'] else e.reparto)
              for e in db.scalars(select(Entrada).where(Entrada.senal == senal).order_by(Entrada.crudo))}
    return Response(json.dumps(salida, ensure_ascii=False, indent=1), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="{senal}.json"'})


@app.get('/api/historial')
def historial(db: Session = Depends(sesion_db), _=Depends(usuario_actual)):
    lista = list(db.scalars(select(Corrida).order_by(Corrida.creada)))
    hace_una_semana = dt.datetime.now() - dt.timedelta(days=7)
    grillas = sum(m.minutos_a_mano // MINUTOS_A_MANO for m in lista)
    return {
        'corridas': [{'id': c.id, 'senal': c.senal, 'creada': c.creada.isoformat(timespec='minutes'),
                      'capas': c.capas, 'grillas': c.minutos_a_mano // MINUTOS_A_MANO} for c in lista],
        'nombres_aprobados': db.scalar(select(func.count()).select_from(Entrada)),
        'al_modelo_esta_semana': sum(c.capas.get('modelo', 0) + c.capas.get('sin propuesta', 0)
                                     for c in lista if c.creada >= hace_una_semana),
        'horas_ahorradas': round(grillas * (MINUTOS_A_MANO - MINUTOS_CON_LA_HERRAMIENTA) / 60, 1),
        'grillas': grillas,
    }
