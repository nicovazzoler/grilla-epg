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
# Lo que puede venir pegado al nombre y el modelo puede separar a su columna.
COLUMNAS_DEL_NOMBRE = {'Temp.': 'número de temporada', 'Tít. Temp.': 'año o nombre de la temporada (ej. 2026 de un torneo)',
                       'Año': 'año de una película', 'Cap.': 'número de capítulo o episodio',
                       'Título': 'título del episodio, partido o etapa'}
NUMERICAS = {'Temp.', 'Tít. Temp.', 'Año', 'Cap.'}


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
    """Una entrada del diccionario como {columna: valor}. Las que guardan solo un texto son el Programa."""
    return {'Programa': valor} if isinstance(valor, str) else dict(valor)


def limpiar_reparto(propuesta):
    """Programa y las columnas permitidas, con los números como números."""
    salida = {'Programa': str(propuesta.get('Programa') or '').strip()}
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
        'Para cada uno, proponé cómo se escribe el Programa según las reglas. Si el texto trae pegado algo que va '
        f'en otra columna, separalo. Columnas posibles:\n{columnas}\n'
        'Poné solo las columnas que el texto trae de verdad. Si no sabés qué programa es, decilo en "nota" '
        'en vez de inventar.\n\n'
        f'Ejemplos ya aprobados (como vino → como va):\n{json.dumps(ejemplos, ensure_ascii=False, indent=1)}\n\n'
        f'Nombres nuevos:\n{json.dumps(crudos, ensure_ascii=False)}\n\n'
        'Contestá SOLO un JSON: {"<como vino>": {"Programa": "<como va>", "<columna>": <valor>, "nota": "<vacío o la duda>"}}'
    )


def proponer_con_modelo(senal, crudos, diccionario):
    """{crudo: {'Programa', columnas..., 'nota'}} propuesto por el modelo, o None si no hay clave o falló el pedido."""
    clave = leer_clave()
    if not clave:
        print('  (sin ANTHROPIC_API_KEY: lo nuevo queda pendiente sin propuesta)')
        return None
    reglas = (AQUI / 'reglas' / f'{senal}.md').read_text(encoding='utf-8')
    # temperature 0: ante el mismo pedido, la misma respuesta.
    cuerpo = json.dumps({'model': MODELO, 'max_tokens': 4000, 'temperature': 0, 'system': reglas,
                         'messages': [{'role': 'user', 'content': pedido_al_modelo(crudos, diccionario)}]}).encode()
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
    """{crudo: reparto} para el Excel, los pendientes a aprobar y cuántos resolvió cada capa."""
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

    propuestas = proponer_con_modelo(senal, al_modelo, diccionario) if al_modelo else {}
    for crudo in al_modelo:
        p = (propuestas or {}).get(crudo) or {}
        if (r := limpiar_reparto(p))['Programa']:
            repartos[crudo] = r
            pendientes.append({'crudo': crudo, 'propuesta': r, 'capa': 'modelo', 'nota': p.get('nota') or ''})
            capas['modelo'] += 1
        else:
            # Sin propuesta sale como vino: se ve en el Excel y queda pendiente.
            repartos[crudo] = {'Programa': crudo}
            pendientes.append({'crudo': crudo, 'propuesta': {}, 'capa': 'sin propuesta', 'nota': ''})
            capas['sin propuesta'] += 1
    return repartos, pendientes, capas


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
    repartos, pendientes, capas = resolver_nombres(a.senal, crudos, diccionario)
    sin_aprobar = {p['crudo'] for p in pendientes}

    for f in filas:
        if f['crudo'] is None:
            continue
        for col, valor in repartos[f['crudo']].items():
            # Lo que el lector sacó de la grilla manda sobre lo que se separó del nombre.
            if col == 'Programa' or f['datos'].get(col) in (None, ''):
                f['datos'][col] = valor
        if f['crudo'] in sin_aprobar:
            f['datos']['Revisar'] = 'sí'
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
