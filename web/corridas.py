"""Lo que hace la web con procesar.py: crear una corrida, armar su EPG con el diccionario de ese momento y aprobar."""
import datetime as dt
import importlib
import re
import tempfile
from pathlib import Path
from sqlalchemy import select
from escribir_epg import DIAS, FIJAS, errores_de_formato, fila_de, guardar, minutos, orden, IDIOMAS
from procesar import (MINUTOS_A_MANO, armar, avisos, conocido, crear_patron, leer_grillas, limpiar_reparto,
                      resolver_nombres, senales)
from web.modelos import Corrida, Entrada, Pendiente, Senal, ahora_utc, iso_utc


def detectar_senal(nombres):
    """La señal que reconoce todos los archivos por su nombre, o None si no hay una sola."""
    candidatas = [s for s in senales()
                  if (patron := getattr(importlib.import_module(f'senales.{s}'), 'ARCHIVOS', None))
                  and all(re.search(patron, n, re.I) for n in nombres)]
    return candidatas[0] if len(candidatas) == 1 else None


def nombre_de(db, senal):
    """El nombre de la señal: el que se le puso en la pantalla o, si no, el del lector."""
    if propio := db.get(Senal, senal):
        return propio.nombre
    return importlib.import_module(f'senales.{senal}').NOMBRE


def diccionario(db, senal):
    return {e.crudo: e.reparto for e in db.scalars(select(Entrada).where(Entrada.senal == senal))}


def a_json(leido):
    filas = [{**f, 'inicio': f['inicio'].isoformat()} for f in leido['filas']]
    return {**leido, 'cierre': leido['cierre'].isoformat(), 'filas': filas}


def de_json(leido):
    filas = [{**f, 'datos': dict(f['datos']), 'inicio': dt.datetime.fromisoformat(f['inicio'])} for f in leido['filas']]
    return {**leido, 'cierre': dt.datetime.fromisoformat(leido['cierre']), 'filas': filas}


def contextos(filas, nombres):
    """Para cada nombre, dónde aparece por primera vez, qué va antes y después y cuántas veces pasa."""
    salida = {}
    for i, f in enumerate(filas):
        if (crudo := f['crudo']) is None:
            continue
        if crudo in salida:
            salida[crudo]['veces'] += 1
            continue
        vecino = lambda j: nombres.get(filas[j]['crudo'], filas[j]['datos'].get('TIT PRINC')) \
            if 0 <= j < len(filas) else None
        salida[crudo] = {'dia': f'{DIAS[f["inicio"].weekday()][:3].lower()} {f["inicio"]:%d/%m}',
                         'hora': f'{f["inicio"]:%H:%M}', 'antes': vecino(i - 1), 'despues': vecino(i + 1), 'veces': 1}
    return salida


def crear(db, senal, rutas, nombres_archivos, horas, semanal):
    """Lee las grillas, resuelve los nombres con el diccionario de la base y guarda la corrida con sus pendientes.
    Puede levantar Frenado (horario fuera de orden) o SystemExit (un lector que no entiende el archivo)."""
    leido = leer_grillas(senal, rutas, horas)
    dicc = diccionario(db, senal)
    crudos = list(dict.fromkeys(f['crudo'] for f in leido['filas'] if f['crudo'] is not None))
    repartos, pendientes, capas, problema = resolver_nombres(senal, crudos, dicc)
    corrida = Corrida(senal=senal, archivos=nombres_archivos, semanal=semanal, leido=a_json(leido), capas=capas,
                      problema_modelo=problema, minutos_a_mano=MINUTOS_A_MANO * len(rutas))
    nombres = {c: r.get('TIT PRINC') for c, r in repartos.items()}
    lugar = contextos(leido['filas'], nombres)
    for p in pendientes:
        corrida.pendientes.append(Pendiente(crudo=p['crudo'], propuesta=p['propuesta'], capa=p['capa'],
                                            nota=p['nota'], contexto=lugar[p['crudo']]))
    db.add(corrida)
    db.commit()
    return corrida


def epg(db, corrida):
    """Las filas del EPG con el diccionario de ahora: lo aprobado manda y lo que falta sale con la propuesta."""
    leido = de_json(corrida.leido)
    # Los eventos del semanal llevan el nombre de la señal, que se puede haber cambiado después de la corrida.
    leido['etiqueta'] = nombre_de(db, corrida.senal)
    dicc = diccionario(db, corrida.senal)
    propuestas = {p.crudo: p.propuesta for p in corrida.pendientes}
    repartos, sin_aprobar = {}, set()
    for crudo in {f['crudo'] for f in leido['filas'] if f['crudo'] is not None}:
        if ya := conocido(crudo, dicc):
            repartos[crudo] = ya[0]
        else:
            repartos[crudo] = propuestas.get(crudo) or {'TIT PRINC': crudo}
            if not repartos[crudo].get('TIT PRINC'):
                repartos[crudo] = {**repartos[crudo], 'TIT PRINC': crudo}
            sin_aprobar.add(crudo)
    filas, _ = armar(corrida.senal, leido, repartos, sin_aprobar, corrida.semanal)
    return leido, filas


def vista(db, corrida):
    """Lo que muestra la pantalla de una corrida: resumen, pendientes y el EPG como tabla."""
    leido, filas = epg(db, corrida)
    idioma = leido.get('idioma', 'es')
    tabla = [fila_de(b, idioma) for b in filas]
    principal = IDIOMAS[idioma].get('TIT PRINC', 'TIT PRINC')
    columnas = [c for c in orden(idioma) if c == principal or any(t.get(c) not in (None, '') for t in tabla)]
    total = sum(minutos(b) for b in filas)
    return {
        'id': corrida.id, 'senal': corrida.senal, 'creada': iso_utc(corrida.creada),
        'archivos': corrida.archivos, 'semanal': corrida.semanal, 'capas': corrida.capas,
        'problema_modelo': corrida.problema_modelo,
        'pendientes': [{'id': p.id, 'crudo': p.crudo, 'propuesta': p.propuesta, 'capa': p.capa, 'nota': p.nota,
                        'contexto': p.contexto, 'estado': p.estado} for p in corrida.pendientes],
        'epg': {
            'columnas': FIJAS + columnas,
            'filas': [[n, DIAS[b['inicio'].weekday()], f'{b["inicio"]:%d/%m/%Y}', f'{b["inicio"]:%H:%M}', t['DUR'],
                       *(t.get(c) for c in columnas)] for n, (b, t) in enumerate(zip(filas, tabla), 1)],
            'minutos': total, 'dias': round(total / 1440, 2),
            'errores': errores_de_formato(filas, idioma), 'avisos': avisos(filas),
        },
    }


def excel(db, corrida):
    """(nombre del archivo, bytes) del EPG armado con el diccionario de ahora."""
    leido, filas = epg(db, corrida)
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(guardar(filas, leido['canal'], carpeta, leido.get('idioma', 'es')))
        return ruta.name, ruta.read_bytes()


def guardar_entrada(db, senal, crudo, reparto_, capa):
    entrada = db.scalar(select(Entrada).where(Entrada.senal == senal, Entrada.crudo == crudo))
    if entrada is None:
        entrada = Entrada(senal=senal, crudo=crudo)
        db.add(entrada)
    entrada.reparto, entrada.capa, entrada.aprobada = reparto_, capa, ahora_utc()


def aprobar(db, pendiente, propuesta, capa=None, patron=False):
    """Pasa el nombre al diccionario de la señal y, con patron, también todo lo que empiece igual.
    Devuelve (reparto guardado, clave del patrón o None), o None si no tiene título."""
    r = limpiar_reparto(propuesta)
    r.pop('PATRON', None)
    if not r['TIT PRINC']:
        return None
    senal = pendiente.corrida.senal
    nuevo = crear_patron(pendiente.crudo, r) if patron else None
    if nuevo:
        guardar_entrada(db, senal, nuevo[0], nuevo[1], 'patrón')
    # Con un patrón que resuelve solo, el nombre exacto sobra: el patrón ya lo cubre.
    if not nuevo or nuevo[1]['RESTO']['estilo'] == 'modelo':
        guardar_entrada(db, senal, pendiente.crudo, r, capa or pendiente.capa)
    db.flush()
    # Lo que quedó resuelto queda resuelto en todas las corridas de la señal: el mismo nombre y,
    # si se creó un patrón, los otros capítulos del programa.
    dicc = diccionario(db, senal)
    for otro in db.scalars(select(Pendiente).join(Corrida).where(
            Corrida.senal == senal, Pendiente.estado != 'aprobado')):
        if otro.crudo == pendiente.crudo or (nuevo and conocido(otro.crudo, dicc)):
            otro.estado = 'aprobado'
    db.commit()
    return r, nuevo[0] if nuevo else None
