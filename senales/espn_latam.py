"""ESPN LATAM y Premium: la "Programming Grid" en .xls, una fila por programa con inicio, fin, tipo de aire y un título
de varios renglones (programa, estadio, ciudad, "TAPE: fecha"). ESPN ING usa este mismo lector."""
import collections
import datetime as dt
import re
import unicodedata
from pathlib import Path
import xlrd

NOMBRE = 'ESPN LATAM'
# Las ING vienen igual pero son otra familia, con su diccionario: este lector no las toma.
CODIGOS_ING = ('1A', '4A', '76A', '99A')
ARCHIVOS = r'^(?!(?:' + '|'.join(CODIGOS_ING) + r') )\d+A - Programming Grid.*\.xls$'
COLUMNAS = {'fecha': 'Date', 'inicio': 'Start', 'fin': 'End', 'emision': 'Airing #',
            'titulo': 'Title / Competitor / Site / Tape Date', 'cc': 'Closed Caption', 'tipo': 'Type',
            'cargada': 'Last Fmt Change'}
TT = {'LIVE': '(v)', 'TAPE': '(g)', 'SAME DAY': '(d)', 'LIVE TAPE TO AIR': '(g)'}
A_CONFIRMAR = 'A confirmar'
HUECO_MINIMO = dt.timedelta(minutes=10)
# El EPG no acepta más de 720 minutos: un hueco más largo se tapa en tramos.
TRAMO_MAXIMO = dt.timedelta(minutes=720)
DURACION_COMPACTO = dt.timedelta(minutes=60)
COMPACTO = 'Compacto - '
# El nombre viene como "<torneo> <deporte> <partido>": el deporte es lo único fijo para saber dónde se corta.
DEPORTES = ('Soccer', 'Football', 'Basketball', 'Hockey', 'Rugby Union', 'Rugby League', 'Tennis', 'Boxing',
            'Baseball', 'Volleyball', 'Golf', 'Motor Sports', 'Motorcycle Racing', 'Cricket', 'Handball', 'MMA')
PARTIDO = re.compile(r'^(.*?\b(?:' + '|'.join(DEPORTES) + r'))\s+(.+?\svs\.\s.+)$')
# Más amplio que marcas.ETAPA: en ESPN un paréntesis con estas palabras siempre es la instancia.
ETAPA = re.compile(r'\b(?:Final|Semifinal|Quarterfinal|Cuartos|Octavos|Jornada|Fecha|Ronda|Round|Ruedas|Fase|D[ií]a|'
                   r'Day|Championship|Game|Leg|Ida|Vuelta|Playoff)', re.I)
PAIS = re.compile(r'\([A-Z]{3}\)')
# "Goles de LaLiga 2026-2027"; en "Campeón UCL 2025-2026" la temporada es parte del título de la cápsula.
TEMPORADA = re.compile(r'\s+(\d{4}-(?:\d{4}|\d{2}))$')
GRAN_PREMIO = re.compile(r'^(?:GP\b|.*\bGrand Prix\b)')


def limpio(texto):
    t = str(texto or '').replace('\xa0', ' ').replace('’', "'").translate(str.maketrans('øØ', 'oO'))
    # El EPG no lleva letras fuera de latin-1: "Plzeň" va "Plzen".
    t = ''.join(c if ord(c) < 256 else unicodedata.normalize('NFKD', c)[0] for c in t)
    return ' '.join(t.split())


def renglones(titulo):
    """(nombre, estadio o None): el primer renglón es el programa, el segundo el estadio; la ciudad y el TAPE no van."""
    todos = [limpio(r) for r in str(titulo).replace('\r', '').split('\n') if r.strip()]
    sitio = [r for r in todos[1:] if not r.startswith('TAPE:')]
    return (todos[0] if todos else ''), (sitio[0] if sitio else None)


def sin_numeral(texto):
    return ' '.join(texto.replace('#', ' ').split())


def instancia_al_final(texto, todas=False):
    """(texto sin la instancia, instancia o None). Con todas, cualquier paréntesis que no sea un país ("(ARG)")."""
    m = re.search(r'\s*\(([^()]+)\)$', texto)
    if not m or PAIS.fullmatch(m.group(0).strip()) or not (todas or ETAPA.search(m.group(1))):
        return texto, None
    return texto[:m.start()], sin_numeral(m.group(1))


def capitulo(*partes):
    return ', '.join(p for p in partes if p) or None


def partido_de(nombre, estadio):
    """(torneo con el deporte, TIT CAP, si es un compacto) o None si el nombre no es un partido."""
    if not (m := PARTIDO.match(nombre)):
        return None
    torneo, partido = m.group(1), m.group(2)
    compacto = partido.startswith('Compactos ')
    partido = partido.removeprefix('Compactos ')
    equipos, instancia = instancia_al_final(partido, todas=True)
    equipos = re.sub(r'(^|\s)#\d+\s', r'\1', equipos)
    return torneo, capitulo(equipos, instancia, estadio), compacto


def gran_premio(nombre):
    """("Fórmula 1 - Prácticas", "GP Las Vegas - Prácticas 1"): el GP cambia cada semana y va al capítulo."""
    # "MotoGP- Repsol Grand Prix of Portugal" también separa: el guion con espacio de un solo lado.
    partes = re.split(r'\s+-\s+|(?<=\S)-\s+', nombre)
    if len(partes) < 2:
        return nombre, None
    quedan, cambia = [partes[0]], []
    for parte in partes[1:]:
        if GRAN_PREMIO.match(parte):
            cambia.append(parte)
        elif m := re.match(r'^(.+?)\s+(GP\s.+)$', parte):
            quedan.append(m.group(1))
            cambia.append(m.group(2))
        elif cambia and (m := re.match(r'^(.+?)\s*#(\d+)$', parte)):
            quedan.append(m.group(1))
            cambia.append(f'{m.group(1)} {m.group(2)}')
        else:
            quedan.append(parte)
    return (' - '.join(quedan), ' - '.join(cambia)) if cambia else (nombre, None)


def separar(nombre, estadio):
    """(crudo para el diccionario, {columna: valor}, si es un evento, si es un compacto)."""
    if partido := partido_de(nombre, estadio):
        torneo, cap, compacto = partido
        return torneo, {'TIT CAP': cap}, True, compacto
    datos = {}
    nombre, instancia = instancia_al_final(nombre)
    if instancia:
        datos['TIT CAP'] = capitulo(instancia, estadio)
    nombre, gp = gran_premio(nombre)
    if gp:
        datos['TIT CAP'] = capitulo(gp, datos.get('TIT CAP'))
    elif m := re.search(r'\s+-\s+([^-]+?)\s*#(\d+)$', nombre):
        # "LPF 2026 - Resumen Fecha #16": lo que cambia cada semana va al capítulo.
        datos['TIT CAP'] = capitulo(f'{m.group(1)} {m.group(2)}', datos.get('TIT CAP'))
        nombre = f'{nombre[:m.start()]} - {m.group(1)}'
    elif m := re.search(r'\s+#(\d+)$', nombre):
        datos['NRO CAP'] = int(m.group(1))
        nombre = nombre[:m.start()]
    if (m := TEMPORADA.search(nombre)) and 'Campe' not in nombre:
        datos['TIT TEMP'] = m.group(1)
        nombre = nombre[:m.start()]
    return nombre, datos, bool(instancia or gp), False


def hora(fecha, valor):
    if isinstance(valor, dt.time):
        return dt.datetime.combine(fecha.date(), valor)
    h, m = map(int, str(valor).strip().split(':')[:2])
    return fecha + dt.timedelta(hours=h, minutes=m)


def filas_de(archivo, horas_corregidas):
    """Las filas válidas de la grilla, en orden: la grilla trae filas basura ("a" en la fecha y el resto vacío)."""
    hoja = xlrd.open_workbook(archivo).sheet_by_index(0)
    cab = [str(c).strip() for c in hoja.row_values(0)]
    col = {k: cab.index(v) for k, v in COLUMNAS.items() if v in cab}
    salida = []
    for n in range(1, hoja.nrows):
        v = hoja.row_values(n)
        if not re.fullmatch(r'\d{2}/\d{2}/\d{4}', str(v[col['fecha']]).strip()):
            continue
        dia = dt.datetime.strptime(v[col['fecha']].strip(), '%d/%m/%Y')
        inicio = hora(dia, horas_corregidas.get(n + 1, v[col['inicio']]))
        fin = hora(dia, v[col['fin']])
        if fin <= inicio:
            fin += dt.timedelta(days=1)
        emision = str(v[col['emision']]).strip()
        salida.append({'n': n + 1, 'inicio': inicio, 'fin': fin, 'v': v, 'col': col, 'valores': tuple(map(str, v)),
                       'orden': (str(v[col['cargada']]).strip() if 'cargada' in col else '',
                                 int(emision) if emision.isdigit() else 0)})
    return salida


def sin_superpuestos(filas):
    """Dos programas a la misma hora: va el que se cargó último ("Last Fmt Change" y, si viene vacía, el Airing # más
    alto). Los idénticos se borran todos: el hueco que dejan se tapa con "A confirmar"."""
    salida = []
    for _, grupo in _por_inicio(filas):
        if len(grupo) == 1:
            salida += grupo
            continue
        veces = collections.Counter(f['valores'] for f in grupo)
        if distintas := [f for f in grupo if veces[f['valores']] == 1]:
            salida.append(max(distintas, key=lambda f: f['orden']))
    return salida


def _por_inicio(filas):
    grupos = []
    for f in filas:
        if grupos and grupos[-1][0] == f['inicio']:
            grupos[-1][1].append(f)
        else:
            grupos.append((f['inicio'], [f]))
    return grupos


def huecos(desde, hasta):
    filas = []
    while desde < hasta:
        filas.append({'ref': f'hueco {desde:%d/%m %H:%M}', 'inicio': desde, 'crudo': None, 'tipo': None, 'ciclo': None,
                      'datos': {'TIT PRINC': A_CONFIRMAR}})
        desde += TRAMO_MAXIMO
    return filas


def leer_grilla(archivos, horas_corregidas, etiqueta, compactos):
    """El leer() de la familia; con compactos, un partido de hasta 60 minutos es un compacto."""
    filas, fin_anterior = [], None
    for archivo in archivos:
        for f in sin_superpuestos(filas_de(archivo, horas_corregidas)):
            v, col = f['v'], f['col']
            if fin_anterior and f['inicio'] - fin_anterior >= HUECO_MINIMO:
                filas += huecos(fin_anterior, f['inicio'])
            nombre, estadio = renglones(v[col['titulo']])
            crudo, datos, evento, compacto = separar(nombre, estadio)
            datos.update({'TT': TT.get(limpio(v[col['tipo']]).upper()), 'CC': 'X' if limpio(v[col['cc']]) else None})
            corto = PARTIDO.match(nombre) and f['fin'] - f['inicio'] <= DURACION_COMPACTO
            compacto = compactos and (compacto or bool(corto))
            filas.append({'ref': f'fila {f["n"]}', 'inicio': f['inicio'], 'crudo': crudo,
                          'tipo': 'evento' if evento else None, 'ciclo': None, 'compacto': compacto, 'datos': datos})
            fin_anterior = f['fin']
    codigo = re.match(r'\s*(\d+A)\b', Path(archivos[0]).name)
    return {'canal': f'ESPN_{codigo.group(1) if codigo else "LATAM"}', 'etiqueta': etiqueta, 'idioma': 'es',
            'filas': filas, 'cierre': fin_anterior}


def leer(archivos, horas_corregidas):
    return leer_grilla(archivos, horas_corregidas, NOMBRE, compactos=True)


def copiar_titulos(filas, columnas=(('TIT ING', 'TIT PRINC'), ('TIT CAP ING', 'TIT CAP'))):
    """El título y el capítulo también en inglés (y en portugués en Brasil): después se decide en cuáles no van."""
    for f in filas:
        for destino, origen in columnas:
            if f['datos'].get(destino) in (None, ''):
                f['datos'][destino] = f['datos'].get(origen)


def completar(filas):
    # El diccionario guarda el torneo sin "Compacto - ": que lo sea o no lo decide la duración de cada fila.
    for f in filas:
        titulo = f['datos'].get('TIT PRINC') or ''
        if f['crudo'] is not None:
            titulo = titulo.removeprefix(COMPACTO)
            if f.get('compacto') and not titulo.startswith('ESPN Compact'):
                titulo = COMPACTO + titulo
            f['datos']['TIT PRINC'] = titulo
    copiar_titulos(filas)
