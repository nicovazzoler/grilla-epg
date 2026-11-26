"""ESPN LATAM y Premium: la "Programming Grid" en .xls, una fila por programa con inicio, fin, tipo de aire y un título
de varios renglones (programa, estadio, ciudad, "TAPE: fecha"). ESPN ING usa este mismo lector."""
import datetime as dt
import re
import unicodedata
from pathlib import Path
import xlrd
from escribir_epg import TEXTO_CORTO

NOMBRE = 'ESPN LATAM'
# Las ING vienen igual pero son otra familia, con su diccionario: este lector no las toma.
CODIGOS_ING = ('1A', '4A', '76A', '99A')
ARCHIVOS = r'^(?!(?:' + '|'.join(CODIGOS_ING) + r') )\d+A - Programming Grid.*\.xls$'
COLUMNAS = {'fecha': 'Date', 'inicio': 'Start', 'fin': 'End', 'codigo': 'Sport Code',
            'titulo': 'Title / Competitor / Site / Tape Date', 'cc': 'Closed Caption', 'tipo': 'Type'}
TT = {'LIVE': '(v)', 'TAPE': '(g)', 'SAME DAY': '(d)', 'LIVE TAPE TO AIR': '(g)'}
A_CONFIRMAR = 'A confirmar'
HUECO_MINIMO = dt.timedelta(minutes=5)
# El EPG no acepta más de 720 minutos: un hueco más largo se tapa en tramos.
TRAMO_MAXIMO = dt.timedelta(minutes=720)
# Un partido corto que no es en vivo es un compacto.
DURACION_COMPACTO = dt.timedelta(minutes=80)
COMPACTO = 'Compacto - '
# El aviso va por el código del programa (Sport Code): sirve para elegir bien la edición al pautar.
AVISOS = {'SRMB': 'OJO! EDICIÓN DE USA', 'SRLB': 'OJO! EDICIÓN DE USA', 'SRCNO': 'OJO! EDICIÓN CHILE',
          'BOKS': "OJO! EDICIÓN 'ES EL SHOW'"}
# El nombre viene como "<torneo> <deporte> <partido>": el deporte es lo único fijo para saber dónde se corta.
DEPORTES = ('Soccer', 'Football', 'Basketball', 'Hockey', 'Rugby Union', 'Rugby League', 'Tennis', 'Boxing',
            'Baseball', 'Volleyball', 'Golf', 'Motor Sports', 'Motorcycle Racing', 'Cricket', 'Handball', 'MMA',
            'Wrestling')
PARTIDO = re.compile(r'^(.*?\b(?:' + '|'.join(DEPORTES) + r'))\s+(.+?\svs\.\s.+)$')
# Más amplio que marcas.ETAPA: en ESPN un paréntesis con estas palabras siempre es la instancia.
ETAPA = re.compile(r'\b(?:Final|Semifinal|Quarterfinal|Cuartos|Octavos|Jornada|Fecha|Ronda|Round|Ruedas|Fase|D[ií]a|'
                   r'Day|Championship|Game|Leg|Ida|Vuelta|Playoff|Play-In|Consolation|Place|Bracket|Group|Grupo|'
                   r'Regional|Heat|Qualif|Clasificaci)', re.I)
# El lugar va solo en torneos y eventos: un programa (de estudio o desde un estadio) no lo lleva.
EVENTO = re.compile(r'\b(?:Championships?|Campeonato|Cup|Copa|Tournament|Torneo|Invitational|Classic|Open)\b')
PROGRAMA = re.compile(r'\b(?:Highlights|Show|Film|Live|Countdown|Journey|Tonight|Today)\b')
# "MLB Baseball Milwaukee Brewers": la liga y el deporte seguidos de un equipo es un partido sin rival en la grilla.
LIGA_Y_EQUIPO = re.compile(r'^(?:MLB|NBA|WNBA|NFL|NHL|MLS) (?:Baseball|Basketball|Football|Hockey|Soccer) \S')
# "ESPN Films" es un ciclo de documentales, como los ciclos de cine; el documental es el título.
CICLO = re.compile(r'ESPN (Film(?:e?s)?)(?:\s+(?:Presents|Pres\.|Presented by))?\s*:?\s*', re.I)
# Series documentales: la serie es el programa y lo que sigue, el capítulo.
SERIES = {'30 for 30': r'30 for 30', 'E60': r'E:?60(?: Pictures)?', 'SC Featured': r'(?:SC|SportsCenter) Featured',
          'In Depth with Graham Bensinger': r'In Depth with Graham Bensinger'}
SERIE = re.compile('|'.join(f'(?P<s{i}>{r})' for i, r in enumerate(SERIES.values())), re.I)
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
    """(nombre, [estadio, ciudad, …, país]): el primer renglón es el programa; el TAPE y el "null" no van."""
    todos = [limpio(r) for r in str(titulo).replace('\r', '').split('\n') if r.strip()]
    sitio = [r for r in todos[1:] if not r.startswith('TAPE:')]
    partes = sitio[:1] + [p.strip() for r in sitio[1:] for p in r.split(',')]
    return (todos[0] if todos else ''), [p for p in partes if p and p.lower() != 'null']


def sin_numeral(texto):
    return ' '.join(texto.replace('#', ' ').split())


def instancia_al_final(texto, todas=False):
    """(texto sin la instancia, instancia o None). Con todas, cualquier paréntesis que no sea un país ("(ARG)")."""
    # Admite un paréntesis adentro: "(Final (Partido de Vuelta))".
    m = re.search(r'\s*\(((?:[^()]|\([^()]*\))+)\)$', texto)
    if not m or PAIS.fullmatch(m.group(0).strip()) or not (todas or ETAPA.search(m.group(1))):
        return texto, None
    return texto[:m.start()], sin_numeral(m.group(1))


def capitulo(*partes):
    return ', '.join(p for p in partes if p) or None


def capitulo_con_sitio(equipos, instancia, sitio):
    """(TIT CAP, hasta dónde llegó): todo lo que venga mientras entre en el EPG; si no, hasta el estadio y, si
    tampoco, hasta el último elemento que entre."""
    for hasta, partes in (('todo', [equipos, instancia, *sitio]), ('estadio', [equipos, instancia, *sitio[:1]]),
                          ('instancia', [equipos, instancia]), ('equipos', [equipos])):
        if (cap := capitulo(*partes)) is None or len(cap) <= TEXTO_CORTO:
            return cap, hasta
    return capitulo(equipos)[:TEXTO_CORTO], 'cortado'


def partido_de(nombre, sitio):
    """(torneo con el deporte, TIT CAP, si la grilla dice "Compactos") o None si el nombre no es un partido."""
    if not (m := PARTIDO.match(nombre)):
        return None
    torneo, partido = m.group(1), m.group(2)
    compacto = partido.startswith('Compactos ')
    partido = partido.removeprefix('Compactos ')
    equipos, instancia = instancia_al_final(partido, todas=True)
    equipos = re.sub(r'(^|\s)#\d+\s', r'\1', equipos)
    return torneo, capitulo_con_sitio(equipos, instancia, sitio)[0], compacto


def gran_premio(nombre):
    """("Fórmula 1 - Prácticas", "GP Las Vegas - Prácticas 1"): el GP cambia cada semana; el capítulo lleva todo lo
    que sigue al primer guion, para no perder la práctica, la clasificación o la carrera."""
    # "MotoGP- Repsol Grand Prix of Portugal" también separa: el guion con espacio de un solo lado.
    partes = re.split(r'\s+-\s+|(?<=\S)-\s+', nombre)
    if len(partes) < 2:
        return nombre, None
    quedan, hay_gp = [partes[0]], False
    for parte in partes[1:]:
        if GRAN_PREMIO.match(parte):
            hay_gp = True
        elif m := re.match(r'^(.+?)\s+GP\s.+$', parte):
            hay_gp = True
            quedan.append(m.group(1))
        else:
            quedan.append(re.sub(r'\s*#\d+$', '', parte))
    if not hay_gp:
        return nombre, None
    return ' - '.join(quedan), ' - '.join(sin_numeral(p) for p in partes[1:])


def sin_mayusculas(texto):
    """'LANCE (Part 1)' -> 'Lance (Part 1)': una palabra toda en mayúsculas de 5 letras o más no es una sigla."""
    return re.sub(r'\b[A-ZÁÉÍÓÚÑ]{5,}\b', lambda m: m.group(0).title(), texto)


def limpiar_capitulo(texto):
    texto = re.sub(r'\s+(?:Presented|Pres\.|presented) by\s+[^()]+$', '', texto.strip(' :-–"'))
    return sin_mayusculas(texto.strip(' :-–"')) or None


def serie_o_ciclo(nombre):
    """(crudo, TIT CAP, ciclo) si es un documental de una serie ("30 for 30: Lance") o del ciclo ESPN Films."""
    ciclo = None
    if m := CICLO.search(nombre):
        ciclo, nombre = f'ESPN {m.group(1).title()}', nombre[m.end():]
    if series := list(SERIE.finditer(nombre)):
        ultima = series[-1]
        serie = list(SERIES)[int(next(k for k, v in ultima.groupdict().items() if v)[1:])]
        return serie, limpiar_capitulo(nombre[ultima.end():]), ciclo
    if ciclo:
        return limpiar_capitulo(nombre), None, ciclo
    return None


def separar(nombre, sitio):
    """(crudo para el diccionario, {columna: valor}, si es un evento, si es un compacto)."""
    if partido := partido_de(nombre, sitio):
        torneo, cap, compacto = partido
        return torneo, {'TIT CAP': cap}, True, compacto
    datos, cap = {}, None
    nombre, instancia = instancia_al_final(nombre)
    nombre, gp = gran_premio(nombre)
    if gp:
        cap = gp
    elif m := re.search(r'\s+-\s+([^-]+?)\s*#(\d+)$', nombre):
        # "LPF 2026 - Resumen Fecha #16": lo que cambia cada semana va al capítulo.
        cap = f'{m.group(1)} {m.group(2)}'
        nombre = f'{nombre[:m.start()]} - {m.group(1)}'
    elif m := re.search(r'\s+#(\d+)$', nombre):
        datos['NRO CAP'] = int(m.group(1))
        nombre = nombre[:m.start()]
    if (m := TEMPORADA.search(nombre)) and 'Campe' not in nombre:
        datos['TIT TEMP'] = m.group(1)
        nombre = nombre[:m.start()]
    evento = bool(instancia or gp)
    de_torneo = (EVENTO.search(nombre) or LIGA_Y_EQUIPO.match(nombre)) and not PROGRAMA.search(nombre)
    lugar = sitio if evento or de_torneo else []
    if cap or instancia or lugar:
        datos['TIT CAP'] = capitulo_con_sitio(cap, instancia, lugar)[0]
    return nombre, datos, evento, False


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
        salida.append({'n': n + 1, 'inicio': inicio, 'fin': fin, 'v': v, 'col': col})
    return salida


def sin_superpuestos(filas):
    """Dos programas a la misma hora no se sabe cuál va: se borran todos y ese tramo queda "A confirmar"."""
    return [f for _, grupo in _por_inicio(filas) if len(grupo) == 1 for f in grupo]


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


def leer_grilla(archivos, horas_corregidas, etiqueta):
    """El leer() de la familia."""
    filas, fin_anterior = [], None
    for archivo in archivos:
        for f in sin_superpuestos(filas_de(archivo, horas_corregidas)):
            v, col = f['v'], f['col']
            if fin_anterior and f['inicio'] - fin_anterior >= HUECO_MINIMO:
                filas += huecos(fin_anterior, f['inicio'])
            nombre, sitio = renglones(v[col['titulo']])
            ciclo = None
            if documental := serie_o_ciclo(nombre):
                crudo, cap, ciclo = documental
                datos, evento, compacto = {'TIT CAP': cap, 'CICLO': ciclo}, False, False
            else:
                crudo, datos, evento, compacto = separar(nombre, sitio)
            aire = limpio(v[col['tipo']]).upper()
            datos.update({'TT': TT.get(aire), 'CC': 'X' if limpio(v[col['cc']]) else None})
            corto = bool(PARTIDO.match(nombre)) and f['fin'] - f['inicio'] <= DURACION_COMPACTO
            filas.append({'ref': f'fila {f["n"]}', 'inicio': f['inicio'], 'crudo': crudo,
                          'tipo': 'pelicula' if ciclo else 'evento' if evento else None, 'ciclo': ciclo,
                          'codigo': limpio(v[col['codigo']]), 'compacto': (compacto or corto) and aire != 'LIVE',
                          'datos': datos})
            fin_anterior = f['fin']
    codigo = re.match(r'\s*(\d+A)\b', Path(archivos[0]).name)
    return {'canal': f'ESPN_{codigo.group(1) if codigo else "LATAM"}', 'etiqueta': etiqueta, 'idioma': 'es',
            'filas': filas, 'cierre': fin_anterior}


def leer(archivos, horas_corregidas):
    return leer_grilla(archivos, horas_corregidas, NOMBRE)


def copiar_titulos(filas, columnas=(('TIT ING', 'TIT PRINC'), ('TIT CAP ING', 'TIT CAP'))):
    """El título y el capítulo también en inglés (y en portugués en Brasil): después se decide en cuáles no van."""
    for f in filas:
        for destino, origen in columnas:
            if f['datos'].get(destino) in (None, ''):
                f['datos'][destino] = f['datos'].get(origen)


def poner_compacto(filas, prefijo):
    # El diccionario guarda el torneo sin el prefijo: que sea compacto lo decide cada fila.
    for f in filas:
        if f['crudo'] is None:
            continue
        titulo = (f['datos'].get('TIT PRINC') or '').removeprefix(COMPACTO).removeprefix('Compact - ')
        if f.get('compacto') and not titulo.startswith(('ESPN Compact', 'Compact')):
            titulo = prefijo + titulo
        f['datos']['TIT PRINC'] = titulo


def poner_avisos(filas):
    for f in filas:
        titulo = f['datos'].get('TIT PRINC') or ''
        if (aviso := AVISOS.get(f.get('codigo'))) and not titulo.startswith('OJO!'):
            f['datos']['TIT PRINC'] = f'{aviso} || {titulo}'


def completar(filas):
    poner_compacto(filas, COMPACTO)
    poner_avisos(filas)
    copiar_titulos(filas)
