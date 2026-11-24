"""Arma el EPG de una señal desde sus grillas. Cada señal tiene su lector en senales/; los nombres se corrigen en capas:
diccionario aprobado → parecido de texto → propuesta del modelo, y todo lo nuevo queda para aprobar.
Uso: python procesar.py <señal> <grilla> [<grilla> ...] [--hora FILA=HH:MM ...]"""
import argparse, csv, datetime as dt, difflib, importlib, json, os, re, sys, unicodedata, urllib.request
from pathlib import Path
from escribir_epg import DIAS, errores_de_formato, guardar, minutos, poner_fines
import semanal

AQUI = Path(__file__).parent
MODELO = 'claude-haiku-4-5-20251001'
PARECIDO_MINIMO = 0.85
# Minutos que llevaba armar una grilla a mano: lo que se compara en el registro.
MINUTOS_A_MANO = 20
# Lo que puede venir pegado al nombre y el modelo puede separar a su columna.
COLUMNAS_DEL_NOMBRE = {'NRO TEMP': 'número de temporada', 'TIT TEMP': 'año o nombre de la temporada (ej. 2026 de un torneo)',
                       'AÑO': 'año de una película', 'NRO CAP': 'número de capítulo o episodio',
                       'TIT CAP': 'título del capítulo, partido o etapa'}
NUMERICAS = {'NRO TEMP', 'AÑO', 'NRO CAP'}
# No es una columna: dice qué pasa con el programa en una grilla semanal.
TIPOS = {'pelicula', 'evento', 'programa'}


class Frenado(Exception):
    """Horarios fuera de orden: una de las dos horas está mal tipeada en la grilla."""
    def __init__(self, antes, ahora):
        self.filas = [{'ref': f['ref'], 'inicio': f['inicio'], 'nombre': f['crudo'] or f['datos']['TIT PRINC']}
                      for f in (antes, ahora)]
        super().__init__(
            f'horarios fuera de orden el {DIAS[ahora["inicio"].weekday()]} {ahora["inicio"]:%d/%m}.\n'
            + ''.join(f'  {f["ref"]}: {f["inicio"]:%H:%M} {f["nombre"]}\n' for f in self.filas)
            + 'Una de las dos horas está mal: revisá la grilla.')


def senales():
    return sorted(p.stem for p in (AQUI / 'senales').glob('*.py') if p.stem != '__init__')


def diccionario_de(senal):
    return AQUI / 'diccionario' / f'{senal}.json'


def pendientes_de(senal):
    return AQUI / 'diccionario' / f'{senal}_pendientes.json'


def normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^\w\s]', ' ', sin_tildes.lower()).split())


def reparto(valor):
    """Una entrada del diccionario como {columna: valor}. Las que guardan solo un texto son el título."""
    return {'TIT PRINC': valor} if isinstance(valor, str) else dict(valor)


def limpiar_reparto(propuesta):
    """El título, las columnas permitidas y el TIPO, con los números como números."""
    salida = {'TIT PRINC': str(propuesta.get('TIT PRINC') or '').strip()}
    if (tipo := str(propuesta.get('TIPO') or '').lower()) in TIPOS:
        salida['TIPO'] = tipo
    for col in COLUMNAS_DEL_NOMBRE:
        v = propuesta.get(col)
        if v in (None, ''):
            continue
        if col in NUMERICAS and str(v).isdigit():
            v = int(v)
        salida[col] = v
    return salida


def por_parecido(crudo, diccionario):
    """La clave conocida más parecida, o None. Compara sin tildes, signos ni mayúsculas."""
    n = normalizar(crudo)
    # Un número distinto casi siempre es otro programa (BN 20 y BN 30): esos nunca cuentan como parecidos.
    claves = {normalizar(k): k for k in diccionario if re.findall(r'\d+', normalizar(k)) == re.findall(r'\d+', n)}
    if n in claves:
        return claves[n]
    cerca = difflib.get_close_matches(n, list(claves), n=1, cutoff=PARECIDO_MINIMO)
    return claves[cerca[0]] if cerca else None


def leer_clave():
    if clave := os.environ.get('ANTHROPIC_API_KEY'):
        return clave
    env = AQUI / '.env'
    if env.exists():
        for linea in env.read_text(encoding='utf-8').splitlines():
            if linea.startswith('ANTHROPIC_API_KEY='):
                return linea.split('=', 1)[1].strip().strip('"\'')
    return None


def pedido_al_modelo(crudos, diccionario):
    ejemplos = {k: reparto(v) for k, v in list(diccionario.items())[:40]}
    columnas = '\n'.join(f'- "{c}": {desc}' for c, desc in COLUMNAS_DEL_NOMBRE.items())
    return (
        'Estos nombres de programas de una grilla de TV no están en el diccionario.\n'
        'Para cada uno, proponé cómo se escribe el título (TIT PRINC) según las reglas. Si el texto trae pegado algo que va '
        f'en otra columna, separalo. Columnas posibles:\n{columnas}\n'
        'Poné solo las columnas que el texto trae de verdad. Agregá "TIPO": "pelicula", "evento" (torneo, partido, '
        'evento especial) o "programa" (todo lo que se repite igual cada semana). Si no sabés qué programa es, '
        'decilo en "nota" en vez de inventar.\n\n'
        f'Ejemplos ya aprobados (como vino → como va):\n{json.dumps(ejemplos, ensure_ascii=False, indent=1)}\n\n'
        f'Nombres nuevos:\n{json.dumps(crudos, ensure_ascii=False)}\n\n'
        'Contestá SOLO un JSON: {"<como vino>": {"TIT PRINC": "<como va>", "<columna>": <valor>, "TIPO": "<tipo>", '
        '"nota": "<vacío o la duda>"}}'
    )


def proponer_con_modelo(senal, crudos, diccionario):
    """({crudo: {'TIT PRINC', columnas..., 'nota'}}, None) o (None, por qué no hubo propuesta)."""
    clave = leer_clave()
    if not clave:
        return None, 'sin ANTHROPIC_API_KEY: lo nuevo queda pendiente sin propuesta'
    reglas = (AQUI / 'reglas' / f'{senal}.md').read_text(encoding='utf-8')
    # temperature 0: ante el mismo pedido, la misma respuesta.
    cuerpo = json.dumps({'model': MODELO, 'max_tokens': 4000, 'temperature': 0, 'system': reglas,
                         'messages': [{'role': 'user', 'content': pedido_al_modelo(crudos, diccionario)}]}).encode()
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=cuerpo, headers={
        'x-api-key': clave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            texto = json.load(r)['content'][0]['text']
        return json.loads(texto[texto.index('{'):texto.rindex('}') + 1]), None
    except Exception as e:
        return None, f'no se pudo consultar el modelo ({e}): lo nuevo queda pendiente sin propuesta'


def resolver_nombres(senal, crudos, diccionario):
    """{crudo: reparto} para el Excel, los pendientes a aprobar, cuántos resolvió cada capa y el problema del modelo."""
    repartos, pendientes, al_modelo = {}, [], []
    capas = {'diccionario': 0, 'parecido': 0, 'modelo': 0, 'sin propuesta': 0}
    for crudo in crudos:
        if crudo in diccionario:
            repartos[crudo] = reparto(diccionario[crudo])
            capas['diccionario'] += 1
        elif conocido := por_parecido(crudo, diccionario):
            repartos[crudo] = reparto(diccionario[conocido])
            pendientes.append({'crudo': crudo, 'propuesta': repartos[crudo], 'capa': 'parecido',
                               'nota': f'se parece a "{conocido}"'})
            capas['parecido'] += 1
        else:
            al_modelo.append(crudo)

    propuestas, problema = proponer_con_modelo(senal, al_modelo, diccionario) if al_modelo else ({}, None)
    for crudo in al_modelo:
        p = (propuestas or {}).get(crudo) or {}
        if (r := limpiar_reparto(p))['TIT PRINC']:
            repartos[crudo] = r
            pendientes.append({'crudo': crudo, 'propuesta': r, 'capa': 'modelo', 'nota': p.get('nota') or ''})
            capas['modelo'] += 1
        else:
            # Sin propuesta sale como vino: se ve en el Excel y queda pendiente.
            repartos[crudo] = {'TIT PRINC': crudo}
            pendientes.append({'crudo': crudo, 'propuesta': {}, 'capa': 'sin propuesta', 'nota': ''})
            capas['sin propuesta'] += 1
    return repartos, pendientes, capas, problema


def leer_grillas(senal, archivos, horas):
    """Lo que leyó el lector de la señal. Frena si los horarios no van en orden."""
    leido = importlib.import_module(f'senales.{senal}').leer(archivos, horas)
    for antes, ahora in zip(leido['filas'], leido['filas'][1:]):
        if ahora['inicio'] <= antes['inicio']:
            raise Frenado(antes, ahora)
    return leido


def armar(senal, leido, repartos, sin_aprobar, es_semanal):
    """(filas del EPG con sus fines, cierre): los nombres puestos, lo propio de la señal y, si va, la semana estirada."""
    filas = leido['filas']
    for f in filas:
        if f['crudo'] is None:
            continue
        r = dict(repartos[f['crudo']])
        if tipo := r.pop('TIPO', None):
            f['tipo'] = None if tipo == 'programa' else tipo
        for col, valor in r.items():
            # Lo que el lector sacó de la grilla manda sobre lo que se separó del nombre.
            if col == 'TIT PRINC' or f['datos'].get(col) in (None, ''):
                f['datos'][col] = valor
        if f['crudo'] in sin_aprobar:
            f['datos']['REVISAR'] = 'sí'
    lector = importlib.import_module(f'senales.{senal}')
    if hasattr(lector, 'completar'):
        lector.completar(filas)
    cierre = leido['cierre']
    if es_semanal:
        filas, cierre = semanal.estirar(filas, cierre, leido['etiqueta'])
    poner_fines(filas, cierre)
    return filas, cierre


def avisos(bloques):
    salida = []
    for b in bloques:
        if minutos(b) > 240:
            salida.append(f'{DIAS[b["inicio"].weekday()]} {b["inicio"]:%d/%m %H:%M} {b["datos"]["TIT PRINC"]}: '
                          f'{minutos(b)} min, ¿falta algo después?')
    return salida


def anotar_corrida(senal, archivos, capas):
    """Una fila por corrida en registro.csv: con las semanas se ve cuánto trabaja el modelo y cuánto tiempo se ahorra."""
    registro = AQUI / 'registro.csv'
    nuevo = not registro.exists()
    with registro.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(['fecha', 'señal', 'grillas', *capas, 'minutos a mano (estimado)'])
        w.writerow([f'{dt.datetime.now():%Y-%m-%d %H:%M}', senal, len(archivos), *capas.values(),
                    MINUTOS_A_MANO * len(archivos)])


def main():
    args = argparse.ArgumentParser()
    args.add_argument('senal', choices=senales(), metavar='señal', help=', '.join(senales()))
    args.add_argument('grillas', nargs='+')
    args.add_argument('--hora', action='append', default=[], help='FILA=HH:MM para una hora mal tipeada (RBTV)')
    args.add_argument('--semanal', action='store_true', help='repite la última semana hasta fin de mes')
    a = args.parse_args()
    horas = {int(f): dt.datetime.strptime(h, '%H:%M').time() for f, h in (x.split('=') for x in a.hora)}

    try:
        leido = leer_grillas(a.senal, a.grillas, horas)
    except Frenado as e:
        sys.exit(f'\nFRENADO: {e} En RBTV se pasa la buena con --hora FILA=HH:MM')
    filas = leido['filas']

    dicc_path = diccionario_de(a.senal)
    diccionario = json.loads(dicc_path.read_text(encoding='utf-8')) if dicc_path.exists() else {}
    crudos = list(dict.fromkeys(f['crudo'] for f in filas if f['crudo'] is not None))
    print(f'{len(filas)} programas, {len(crudos)} nombres distintos')
    repartos, pendientes, capas, problema = resolver_nombres(a.senal, crudos, diccionario)
    if problema:
        print(f'  ({problema})')
    filas, cierre = armar(a.senal, leido, repartos, {p['crudo'] for p in pendientes}, a.semanal)
    if a.semanal:
        print(f'Semanal: la última semana se repite; el último programa termina el {cierre:%d/%m %H:%M}')
    idioma = leido.get('idioma', 'es')
    salida = guardar(filas, leido['canal'], AQUI / 'salida', idioma)
    errores = errores_de_formato(filas, idioma)
    pendientes_de(a.senal).write_text(json.dumps(pendientes, ensure_ascii=False, indent=2), encoding='utf-8')
    anotar_corrida(a.senal, a.grillas, capas)

    print('\nNombres:')
    for capa, n in capas.items():
        print(f'  {capa:<14} {n:>3}')
    total = sum(minutos(b) for b in filas)
    print(f'\nTotal: {total} minutos ({total / 1440:g} días)')
    for aviso in avisos(filas):
        print(f'  AVISO: {aviso}')
    if errores:
        print(f'\n{len(errores)} ERRORES DE FORMATO (el sistema los rechazaría):')
        for e in errores[:20]:
            print(f'  {e}')
        if len(errores) > 20:
            print(f'  ... y {len(errores) - 20} más')
    print(f'\nEPG: {salida}')
    if pendientes:
        print(f'{len(pendientes)} nombres para aprobar: python aprobar.py {a.senal}')


if __name__ == '__main__':
    main()
