"""Arma el EPG de RBTV desde la grade semanal. Los nombres se corrigen en capas:
diccionario aprobado → parecido de texto → propuesta del modelo, y todo lo nuevo queda para aprobar.
Uso: python procesar.py <grade.xlsx> [--hora FILA=HH:MM ...]"""
import argparse, datetime as dt, difflib, json, os, re, sys, unicodedata, urllib.request
from pathlib import Path
import openpyxl
from escribir_epg import DIAS, guardar, minutos, poner_fines

AQUI = Path(__file__).parent
DICCIONARIO = AQUI / 'diccionario' / 'rbtv.json'
PENDIENTES = AQUI / 'diccionario' / 'pendientes.json'
REGLAS = AQUI / 'reglas' / 'rbtv.md'
MODELO = 'claude-haiku-4-5-20251001'
PARECIDO_MINIMO = 0.85

SIN_CICLO = re.compile(r'^[^:]+: (.+)$')
INFOMERCIAL = re.compile(r'INFOMERCIAL \d+ MINUTOS')


def limpiar(texto):
    """Lo estructural, que siempre se resuelve igual: (nombre tal como vino, año, capítulo, TT)."""
    t = ' '.join(texto.split()).rstrip(' |:')
    tt = None
    for marca, valor in (('| AO VIVO', '(v)'), ('(AO VIVO)', '(v)'), ('(REPRISE)', '(r)')):
        if marca in t:
            tt, t = valor, t.replace(marca, '').strip(' |')
    t = re.sub(r'\s*\((AD|A2)\)', '', t)
    anio = None
    if m := re.search(r'\s*\((\d{4})\)$', t):
        anio, t = int(m.group(1)), t[:m.start()]
    if INFOMERCIAL.fullmatch(t):
        return 'INFOMERCIAL', None, None, tt
    t = re.sub(r'^PROGRAMA:\s*', '', t)
    cap = None
    if m := re.fullmatch(r'EM REVISTA: PGM (\d+)', t):
        t, cap = 'EM REVISTA', int(m.group(1))
    elif m := SIN_CICLO.match(t):
        t = m.group(1)
    return t, anio, cap, tt


def leer_grade(ruta, horas_corregidas):
    hoja = openpyxl.load_workbook(ruta).worksheets[0]
    filas, fecha = [], None
    for fila in range(12, hoja.max_row + 1):
        hora, prog = hoja.cell(fila, 2).value, hoja.cell(fila, 4).value
        if isinstance(hora, dt.datetime):
            fecha = hora
            continue
        if hora is None or not prog or not str(prog).strip():
            continue
        if isinstance(hora, str):
            hora = dt.datetime.strptime(hora.strip(), '%H:%M:%S').time()
        hora = horas_corregidas.get(fila, hora)
        # El día de la grade va de 06:00 a 06:00: la madrugada es del día calendario siguiente.
        inicio = fecha + dt.timedelta(days=1 if hora.hour < 6 else 0, hours=hora.hour, minutes=hora.minute)
        crudo, anio, cap, tt = limpiar(str(prog))
        filas.append({'fila': fila, 'inicio': inicio, 'crudo': crudo, 'Año': anio, 'Cap.': cap, 'TT': tt})
    return filas


def normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^\w\s]', ' ', sin_tildes.lower()).split())


def por_parecido(crudo, diccionario):
    """La clave conocida más parecida, o None. Compara sin tildes, signos ni mayúsculas."""
    claves = {normalizar(k): k for k in diccionario}
    if (n := normalizar(crudo)) in claves:
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


def proponer_con_modelo(crudos, diccionario):
    """{crudo: {'nombre', 'nota'}} propuesto por el modelo, o None si no hay clave o falló el pedido."""
    clave = leer_clave()
    if not clave:
        print('  (sin ANTHROPIC_API_KEY: quedan pendientes sin propuesta)')
        return None
    ejemplos = dict(list(diccionario.items())[:40])
    pedido = (
        'Estos nombres de programas de TV de una grilla brasileña no están en el diccionario.\n'
        'Para cada uno, proponé cómo se escribe según las reglas. Si no sabés qué programa es, '
        'decilo en "nota" en vez de inventar.\n\n'
        f'Ejemplos ya aprobados (como vino → como va):\n{json.dumps(ejemplos, ensure_ascii=False, indent=1)}\n\n'
        f'Nombres nuevos:\n{json.dumps(crudos, ensure_ascii=False)}\n\n'
        'Contestá SOLO un JSON: {"<como vino>": {"nombre": "<como va>", "nota": "<vacío o la duda>"}}'
    )
    cuerpo = json.dumps({'model': MODELO, 'max_tokens': 2000, 'system': REGLAS.read_text(encoding='utf-8'),
                         'messages': [{'role': 'user', 'content': pedido}]}).encode()
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=cuerpo, headers={
        'x-api-key': clave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            texto = json.load(r)['content'][0]['text']
        texto = texto[texto.index('{'):texto.rindex('}') + 1]
        return json.loads(texto)
    except Exception as e:
        print(f'  (no se pudo consultar el modelo: {e}; quedan pendientes sin propuesta)')
        return None


def resolver_nombres(crudos, diccionario):
    """{crudo: nombre} para el Excel, los pendientes a aprobar y cuántos resolvió cada capa."""
    nombres, pendientes = {}, []
    capas = {'diccionario': 0, 'parecido': 0, 'modelo': 0, 'sin propuesta': 0}
    al_modelo = []
    for crudo in crudos:
        if crudo in diccionario:
            nombres[crudo] = diccionario[crudo]
            capas['diccionario'] += 1
        elif conocido := por_parecido(crudo, diccionario):
            nombres[crudo] = diccionario[conocido]
            pendientes.append({'crudo': crudo, 'propuesta': diccionario[conocido], 'capa': 'parecido',
                               'nota': f'se parece a "{conocido}"'})
            capas['parecido'] += 1
        else:
            al_modelo.append(crudo)

    propuestas = proponer_con_modelo(al_modelo, diccionario) if al_modelo else {}
    for crudo in al_modelo:
        p = (propuestas or {}).get(crudo)
        if p and p.get('nombre'):
            nombres[crudo] = p['nombre']
            pendientes.append({'crudo': crudo, 'propuesta': p['nombre'], 'capa': 'modelo', 'nota': p.get('nota', '')})
            capas['modelo'] += 1
        else:
            # Sin propuesta sale como vino: es visible en el Excel y queda pendiente.
            nombres[crudo] = crudo
            pendientes.append({'crudo': crudo, 'propuesta': '', 'capa': 'sin propuesta', 'nota': ''})
            capas['sin propuesta'] += 1
    return nombres, pendientes, capas


def frenar_si_desordenado(filas):
    for antes, ahora in zip(filas, filas[1:]):
        if ahora['inicio'] <= antes['inicio']:
            sys.exit(f'\nFRENADO: horarios fuera de orden el {DIAS[ahora["inicio"].weekday()]} {ahora["inicio"]:%d/%m}.\n'
                     f'  fila {antes["fila"]}: {antes["inicio"]:%H:%M} {antes["crudo"]}\n'
                     f'  fila {ahora["fila"]}: {ahora["inicio"]:%H:%M} {ahora["crudo"]}\n'
                     f'Una de las dos horas está mal. Revisá la grade y pasá la buena: --hora FILA=HH:MM')


def avisos(bloques):
    dias = {(b['inicio'] - dt.timedelta(hours=6)).date() for b in bloques}
    salida = [] if len(dias) == 7 else [f'la grade cubre {len(dias)} días, no 7']
    for b in bloques:
        if minutos(b) > 240:
            salida.append(f'{DIAS[b["inicio"].weekday()]} {b["inicio"]:%d/%m %H:%M} {b["datos"]["Programa"]}: '
                          f'{minutos(b)} min, ¿falta algo después?')
    return salida


def main():
    args = argparse.ArgumentParser()
    args.add_argument('grade')
    args.add_argument('--hora', action='append', default=[], help='FILA=HH:MM para una hora mal tipeada')
    a = args.parse_args()
    horas = {int(f): dt.datetime.strptime(h, '%H:%M').time() for f, h in (x.split('=') for x in a.hora)}

    diccionario = json.loads(DICCIONARIO.read_text(encoding='utf-8')) if DICCIONARIO.exists() else {}
    filas = leer_grade(a.grade, horas)
    frenar_si_desordenado(filas)

    crudos = list(dict.fromkeys(f['crudo'] for f in filas))
    print(f'{len(filas)} programas en la grade, {len(crudos)} nombres distintos')
    nombres, pendientes, capas = resolver_nombres(crudos, diccionario)

    bloques = [{'inicio': f['inicio'], 'datos': {'Programa': nombres[f['crudo']], 'Año': f['Año'],
                                                  'Cap.': f['Cap.'], 'TT': f['TT']}} for f in filas]
    poner_fines(bloques)
    salida = guardar(bloques, 'RBTV', AQUI / 'salida')
    PENDIENTES.write_text(json.dumps(pendientes, ensure_ascii=False, indent=2), encoding='utf-8')

    print('\nNombres:')
    for capa, n in capas.items():
        print(f'  {capa:<14} {n:>3}')
    print(f'\nTotal: {sum(minutos(b) for b in bloques)} minutos (7 días = 10080)')
    for aviso in avisos(bloques):
        print(f'  AVISO: {aviso}')
    print(f'\nEPG: {salida}')
    if pendientes:
        print(f'{len(pendientes)} nombres para aprobar: python aprobar.py')


if __name__ == '__main__':
    main()
