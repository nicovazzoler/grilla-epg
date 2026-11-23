"""Arma el EPG de una señal desde sus grillas. Cada señal tiene su lector en senales/; los nombres se corrigen en capas:
diccionario aprobado → parecido de texto → propuesta del modelo, y todo lo nuevo queda para aprobar.
Uso: python procesar.py <señal> <grilla> [<grilla> ...] [--hora FILA=HH:MM ...]"""
import argparse, csv, datetime as dt, difflib, importlib, json, os, re, sys, unicodedata, urllib.request
from pathlib import Path
from escribir_epg import DIAS, guardar, minutos, poner_fines

AQUI = Path(__file__).parent
MODELO = 'claude-haiku-4-5-20251001'
PARECIDO_MINIMO = 0.85
# Minutos que llevaba armar una grilla a mano: lo que se compara en el registro.
MINUTOS_A_MANO = 20


def senales():
    return sorted(p.stem for p in (AQUI / 'senales').glob('*.py') if p.stem != '__init__')


def diccionario_de(senal):
    return AQUI / 'diccionario' / f'{senal}.json'


def pendientes_de(senal):
    return AQUI / 'diccionario' / f'{senal}_pendientes.json'


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


def proponer_con_modelo(senal, crudos, diccionario):
    """{crudo: {'nombre', 'nota'}} propuesto por el modelo, o None si no hay clave o falló el pedido."""
    clave = leer_clave()
    if not clave:
        print('  (sin ANTHROPIC_API_KEY: lo nuevo queda pendiente sin propuesta)')
        return None
    ejemplos = dict(list(diccionario.items())[:40])
    pedido = (
        'Estos nombres de programas de una grilla de TV no están en el diccionario.\n'
        'Para cada uno, proponé cómo se escribe según las reglas. Si no sabés qué programa es, '
        'decilo en "nota" en vez de inventar.\n\n'
        f'Ejemplos ya aprobados (como vino → como va):\n{json.dumps(ejemplos, ensure_ascii=False, indent=1)}\n\n'
        f'Nombres nuevos:\n{json.dumps(crudos, ensure_ascii=False)}\n\n'
        'Contestá SOLO un JSON: {"<como vino>": {"nombre": "<como va>", "nota": "<vacío o la duda>"}}'
    )
    reglas = (AQUI / 'reglas' / f'{senal}.md').read_text(encoding='utf-8')
    cuerpo = json.dumps({'model': MODELO, 'max_tokens': 4000, 'system': reglas,
                         'messages': [{'role': 'user', 'content': pedido}]}).encode()
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=cuerpo, headers={
        'x-api-key': clave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            texto = json.load(r)['content'][0]['text']
        return json.loads(texto[texto.index('{'):texto.rindex('}') + 1])
    except Exception as e:
        print(f'  (no se pudo consultar el modelo: {e}; lo nuevo queda pendiente sin propuesta)')
        return None


def resolver_nombres(senal, crudos, diccionario):
    """{crudo: nombre} para el Excel, los pendientes a aprobar y cuántos resolvió cada capa."""
    nombres, pendientes, al_modelo = {}, [], []
    capas = {'diccionario': 0, 'parecido': 0, 'modelo': 0, 'sin propuesta': 0}
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

    propuestas = proponer_con_modelo(senal, al_modelo, diccionario) if al_modelo else {}
    for crudo in al_modelo:
        p = (propuestas or {}).get(crudo)
        if p and p.get('nombre'):
            nombres[crudo] = p['nombre']
            pendientes.append({'crudo': crudo, 'propuesta': p['nombre'], 'capa': 'modelo', 'nota': p.get('nota', '')})
            capas['modelo'] += 1
        else:
            # Sin propuesta sale como vino: se ve en el Excel y queda pendiente.
            nombres[crudo] = crudo
            pendientes.append({'crudo': crudo, 'propuesta': '', 'capa': 'sin propuesta', 'nota': ''})
            capas['sin propuesta'] += 1
    return nombres, pendientes, capas


def frenar_si_desordenado(filas):
    for antes, ahora in zip(filas, filas[1:]):
        if ahora['inicio'] <= antes['inicio']:
            sys.exit(f'\nFRENADO: horarios fuera de orden el {DIAS[ahora["inicio"].weekday()]} {ahora["inicio"]:%d/%m}.\n'
                     f'  {antes["ref"]}: {antes["inicio"]:%H:%M} {antes["crudo"] or antes["datos"]["Programa"]}\n'
                     f'  {ahora["ref"]}: {ahora["inicio"]:%H:%M} {ahora["crudo"] or ahora["datos"]["Programa"]}\n'
                     'Una de las dos horas está mal: revisá la grilla. En RBTV se pasa la buena con --hora FILA=HH:MM')


def avisos(bloques):
    salida = []
    for b in bloques:
        if minutos(b) > 240:
            salida.append(f'{DIAS[b["inicio"].weekday()]} {b["inicio"]:%d/%m %H:%M} {b["datos"]["Programa"]}: '
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
    a = args.parse_args()
    horas = {int(f): dt.datetime.strptime(h, '%H:%M').time() for f, h in (x.split('=') for x in a.hora)}

    lector = importlib.import_module(f'senales.{a.senal}')
    leido = lector.leer(a.grillas, horas)
    filas = leido['filas']
    frenar_si_desordenado(filas)

    dicc_path = diccionario_de(a.senal)
    diccionario = json.loads(dicc_path.read_text(encoding='utf-8')) if dicc_path.exists() else {}
    crudos = list(dict.fromkeys(f['crudo'] for f in filas if f['crudo'] is not None))
    print(f'{len(filas)} programas, {len(crudos)} nombres distintos')
    nombres, pendientes, capas = resolver_nombres(a.senal, crudos, diccionario)

    for f in filas:
        if f['crudo'] is not None:
            f['datos']['Programa'] = nombres[f['crudo']]
    if hasattr(lector, 'completar'):
        lector.completar(filas)
    poner_fines(filas, leido['cierre'])
    salida = guardar(filas, leido['canal'], AQUI / 'salida')
    pendientes_de(a.senal).write_text(json.dumps(pendientes, ensure_ascii=False, indent=2), encoding='utf-8')
    anotar_corrida(a.senal, a.grillas, capas)

    print('\nNombres:')
    for capa, n in capas.items():
        print(f'  {capa:<14} {n:>3}')
    total = sum(minutos(b) for b in filas)
    print(f'\nTotal: {total} minutos ({total / 1440:g} días)')
    for aviso in avisos(filas):
        print(f'  AVISO: {aviso}')
    print(f'\nEPG: {salida}')
    if pendientes:
        print(f'{len(pendientes)} nombres para aprobar: python aprobar.py {a.senal}')


if __name__ == '__main__':
    main()
