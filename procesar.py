"""Arma el EPG de una señal desde sus grillas. Cada señal tiene su lector en senales/; los nombres se corrigen en capas:
diccionario aprobado → patrón de un programa → parecido de texto → propuesta del modelo, y lo nuevo queda para aprobar.
Uso: python procesar.py <señal> <grilla> [<grilla> ...] [--hora FILA=HH:MM ...]"""
import argparse, csv, datetime as dt, difflib, importlib, json, os, re, sys, unicodedata, urllib.request
from pathlib import Path
from escribir_epg import DIAS, errores_de_formato, guardar, minutos, poner_fines
import semanal
from marcas import separar_marcas

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
# "PARECE TERAPIA | RAFA OLIVEIRA": el programa, un separador y lo que cambia cada semana.
CON_SEPARADOR = re.compile(r'^(.+?)\s*(\||:|\s-\s)\s*(.+)$')
# Palabras que van en minúscula en un nombre propio: "Família do Ré Mi", "Ana de la Vega".
CHICAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'na', 'no', 'nas', 'nos', 'a', 'o', 'as', 'os', 'y', 'la', 'el',
          'las', 'los', 'del', 'al', 'en', 'con', 'por', 'para', 'com', 'um', 'uma', 'of', 'the', 'and'}
CAPAS = ('diccionario', 'patrón', 'parecido', 'modelo', 'sin propuesta')


class Frenado(Exception):
    """Horarios fuera de orden: una de las dos horas está mal tipeada en la grilla.
    filas son las dos en conflicto (marcadas) con las dos de antes y las dos de después, para ver cuál no encaja."""
    def __init__(self, filas, i):
        ahora = filas[i]
        self.filas = [{'ref': f['ref'], 'inicio': f['inicio'], 'nombre': f['crudo'] or f['datos']['TIT PRINC'],
                       'conflicto': j in (i - 1, i)}
                      for j, f in enumerate(filas) if i - 3 <= j <= i + 2]
        super().__init__(
            f'horarios fuera de orden el {DIAS[ahora["inicio"].weekday()]} {ahora["inicio"]:%d/%m}.\n'
            + ''.join(f'{"> " if f["conflicto"] else "  "}{f["ref"]}: {DIAS[f["inicio"].weekday()][:3].lower()} {f["inicio"]:%H:%M} {f["nombre"]}\n'
                      for f in self.filas)
            + 'Una de las dos marcadas está mal: revisá la grilla.')


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
    if isinstance(valor, str):
        return {'TIT PRINC': valor}
    return {k: v for k, v in valor.items() if k != 'RESTO'}


def es_patron(valor):
    return isinstance(valor, dict) and 'RESTO' in valor


def con_estilo(texto, estilo):
    """La parte que cambia de un patrón, escrita como se aprendió del ejemplo aprobado."""
    if estilo != 'nombre':
        return texto
    palabras = texto.lower().split()
    return ' '.join(p if i and p in CHICAS else p[:1].upper() + p[1:] for i, p in enumerate(palabras))


def estilo_de(resto, aprobado):
    """'nombre' si se escribió como nombre propio, 'tal cual' si se dejó como vino, y si no 'modelo':
    una frase con nombres propios adentro no se puede escribir bien con una regla."""
    if aprobado == con_estilo(resto, 'nombre'):
        return 'nombre'
    return 'tal cual' if aprobado == resto else 'modelo'


def crear_patron(crudo, aprobado):
    """(clave, valor) del patrón que sale de aprobar así un nombre con separador, o None si no se puede:
    la parte que sigue al separador tiene que haber ido entera a una columna de texto."""
    if not (m := CON_SEPARADOR.match(crudo)):
        return None
    resto = m.group(3).strip()
    columna = next((c for c in COLUMNAS_DEL_NOMBRE if c not in NUMERICAS and aprobado.get(c)
                    and normalizar(str(aprobado[c])) == normalizar(resto)), None)
    if not columna:
        return None
    valor = {k: v for k, v in aprobado.items() if k not in (columna, 'PATRON')}
    valor['RESTO'] = {'columna': columna, 'estilo': estilo_de(resto, str(aprobado[columna]))}
    return f'{m.group(1).strip()} {m.group(2).strip()}', valor


def buscar_patron(crudo, diccionario):
    """(clave, lo que sigue al separador) del patrón más largo que le corresponde al nombre, o None."""
    mejor = None
    for clave, valor in diccionario.items():
        if not es_patron(valor):
            continue
        base, sep = clave[:-1].strip(), clave[-1]
        separador = r'\s-\s' if sep == '-' else re.escape(sep)
        if (m := re.match(re.escape(base) + r'\s*' + separador + r'\s*(.+)$', crudo)) and \
                (mejor is None or len(clave) > len(mejor[0])):
            mejor = (clave, m.group(1).strip())
    return mejor


def reparto_de_patron(valor, resto, escrito=None):
    """El reparto del patrón con la parte que cambia en su columna; escrito, si ya la escribió el modelo."""
    r = reparto(valor)
    r[valor['RESTO']['columna']] = escrito or con_estilo(resto, valor['RESTO']['estilo'])
    return r


def conocido(crudo, diccionario):
    """(reparto, capa) si el nombre ya está resuelto sin preguntar a nadie: por el diccionario o por un patrón
    que no necesita al modelo. Si no, None."""
    if crudo in diccionario:
        return reparto(diccionario[crudo]), 'diccionario'
    if (patron := buscar_patron(crudo, diccionario)) and diccionario[patron[0]]['RESTO']['estilo'] != 'modelo':
        return reparto_de_patron(diccionario[patron[0]], patron[1]), 'patrón'
    return None


def limpiar_reparto(propuesta):
    """El título, las columnas permitidas y el TIPO, con los números como números."""
    salida = {'TIT PRINC': str(propuesta.get('TIT PRINC') or '').strip()}
    if (tipo := str(propuesta.get('TIPO') or '').lower()) in TIPOS:
        salida['TIPO'] = tipo
    if propuesta.get('PATRON') is True:
        salida['PATRON'] = True
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
    claves = {normalizar(k): k for k, v in diccionario.items()
              if not es_patron(v) and re.findall(r'\d+', normalizar(k)) == re.findall(r'\d+', n)}
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
    ejemplos = {k: reparto(v) for k, v in list(diccionario.items())[:40] if not es_patron(v)}
    columnas = '\n'.join(f'- "{c}": {desc}' for c, desc in COLUMNAS_DEL_NOMBRE.items())
    return (
        'Estos nombres de programas de una grilla de TV no están en el diccionario.\n'
        'Para cada uno, proponé cómo se escribe el título (TIT PRINC) según las reglas. Si el texto trae pegado algo que va '
        f'en otra columna, separalo. Columnas posibles:\n{columnas}\n'
        'Poné solo las columnas que el texto trae de verdad. Agregá "TIPO": "pelicula", "evento" (torneo, partido, '
        'evento especial) o "programa" (todo lo que se repite igual cada semana). Si el nombre es un programa '
        'seguido de un separador (| : -) y una parte que cambia cada semana (el invitado, el tema del capítulo), '
        'mandá esa parte a TIT CAP y agregá "PATRON": true; si lo que sigue es parte del nombre del programa '
        '("COPA LIBERTADORES HIGHLIGHTS"), no. Los nombres propios van siempre con mayúscula. Si no sabés qué '
        'programa es, decilo en "nota" en vez de inventar.\n\n'
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
    repartos, pendientes, al_modelo, capitulos = {}, [], [], {}
    capas = dict.fromkeys(CAPAS, 0)
    for crudo in crudos:
        if ya := conocido(crudo, diccionario):
            repartos[crudo], capa = ya
            capas[capa] += 1
        elif patron := buscar_patron(crudo, diccionario):
            # Patrón cuya parte que cambia es una frase: el programa está resuelto, la frase la escribe el modelo.
            capitulos[crudo] = patron
        elif parecido := por_parecido(crudo, diccionario):
            repartos[crudo] = reparto(diccionario[parecido])
            pendientes.append({'crudo': crudo, 'propuesta': repartos[crudo], 'capa': 'parecido',
                               'nota': f'se parece a "{parecido}"'})
            capas['parecido'] += 1
        else:
            al_modelo.append(crudo)

    restos = [resto for _, resto in capitulos.values()]
    pedido = al_modelo + [r for r in restos if r not in al_modelo]
    propuestas, problema = proponer_con_modelo(senal, pedido, diccionario) if pedido else ({}, None)
    for crudo, (clave, resto) in capitulos.items():
        escrito = ((propuestas or {}).get(resto) or {}).get('TIT PRINC')
        repartos[crudo] = reparto_de_patron(diccionario[clave], resto, escrito)
        pendientes.append({'crudo': crudo, 'propuesta': repartos[crudo], 'capa': 'patrón',
                           'nota': f'capítulo de {repartos[crudo]["TIT PRINC"]}: revisá cómo quedó escrito'})
        capas['patrón'] += 1
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


def poner_marcas(fila, idioma):
    """Saca del nombre lo que se escribe igual en todas las señales (TT, DEST, temporada, capítulo, año).
    Lo que el lector ya puso en una columna le gana; una parte ("Parte 2") se suma al título del capítulo."""
    fila['crudo'], marcas = separar_marcas(fila['crudo'], idioma, fila.get('tipo') == 'pelicula')
    datos = fila['datos']
    for columna, valor in marcas.items():
        if columna == 'TIT CAP' and datos.get('TIT CAP'):
            datos['TIT CAP'] = f'{datos["TIT CAP"]} - {valor}'
        elif datos.get(columna) in (None, ''):
            datos[columna] = valor


def leer_grillas(senal, archivos, horas):
    """Lo que leyó el lector de la señal. Frena si los horarios no van en orden."""
    leido = importlib.import_module(f'senales.{senal}').leer(archivos, horas)
    filas = leido['filas']
    for f in filas:
        if f['crudo']:
            poner_marcas(f, leido.get('idioma', 'es'))
    for i in range(1, len(filas)):
        if filas[i]['inicio'] <= filas[i - 1]['inicio']:
            raise Frenado(filas, i)
    return leido


def armar(senal, leido, repartos, sin_aprobar, es_semanal):
    """(filas del EPG con sus fines, cierre): los nombres puestos, lo propio de la señal y, si va, la semana estirada."""
    filas = leido['filas']
    for f in filas:
        if f['crudo'] is None:
            continue
        r = dict(repartos[f['crudo']])
        r.pop('PATRON', None)
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
