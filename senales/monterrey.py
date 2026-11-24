"""Televisa Monterrey (C-4.1, C-8.1): un PDF por semana con un recuadro por programa.
El lunes y el canal salen del nombre del archivo: ...C-4.1_MONTERREY-20261116-20261122.pdf"""
import datetime as dt
import re
import sys
from pathlib import Path
import pdfplumber

NOMBRE = 'Televisa Monterrey'
ARCHIVOS = r'MONTERREY.*\.pdf$'
ARRIBA, ABAJO = 79.2, 747.7          # 00:00 y 24:00 en el PDF
COLUMNAS = [49.1, 122.3, 195.5, 268.7, 341.9, 415.1, 488.4, 561.6]

TITULOS_EN_MAYUS = {'UNAM VS. MONTERREY': 'UNAM vs. Monterrey'}
TITULOS = {'El Guardian de la Esperanza': 'El guardián de la esperanza', 'De Dreamer a Millonaria': 'De dreamer a millonaria',
           'Vuelo a la Libertad': 'Vuelo a la libertad', 'Mentiras, El Musical': 'Mentiras, el musical'}
TT = {'GRABADO': '(g)', 'VIVO': '(v)', 'REPETICIÓN': '(r)'}
SOLO_CICLO = '(ciclo)'
CICLOS = re.compile(r'^(CINE DE ORO|CICLO DE: .+|TELENOVELA|PELICULA MEXICANA)$')
DURACION = re.compile(r'\s*\d:\d{2}$')
RATING = re.compile(r'^(AA|A|B|B15|C|D)$')
ENLACE = re.compile(r'\s*(Enlace Canal 4\.?|EC4)\s*$')
EVENTOS = ('LIGA MX',)
# "lunes" en Proyéctese dice de qué día es la repetición: no es título.
NOTAS = {'lunes'}


def minuto(y):
    return round((y - ARRIBA) / (ABAJO - ARRIBA) * 24 * 4) * 15


def cajas(pdf):
    """(día, minuto de inicio, líneas de texto) de cada recuadro, armado con las líneas negras del PDF."""
    p = pdfplumber.open(pdf).pages[0]
    negras = [r for r in p.rects if r.get('non_stroking_color') in (0, 0.0, (0,), [0])]
    hs = [r for r in negras if r['height'] < 1.2 and r['top'] > ARRIBA - 1]
    vs = [r for r in negras if r['width'] < 1.2]
    salida = []
    for d in range(7):
        xc = (COLUMNAS[d] + COLUMNAS[d + 1]) / 2
        cortes = sorted({ARRIBA, ABAJO, *(r['top'] for r in hs if r['x0'] <= xc <= r['x1'])})
        cortes = [y for i, y in enumerate(cortes) if i == 0 or y - cortes[i - 1] > 2]
        for ya, yb in zip(cortes, cortes[1:]):
            ym = (ya + yb) / 2
            izq = max(r['x0'] for r in vs if r['x0'] < xc and r['top'] <= ym <= r['bottom'])
            der = min(r['x0'] for r in vs if r['x0'] > xc and r['top'] <= ym <= r['bottom'])
            dentro = sorted((c for c in p.chars if izq < (c['x0'] + c['x1']) / 2 < der
                             and ya < (c['top'] + c['bottom']) / 2 < yb), key=lambda c: c['top'])
            # Los caracteres vienen sueltos: se agrupan por renglón y se leen de izquierda a derecha.
            renglones = []
            for c in dentro:
                if renglones and abs(c['top'] - renglones[-1][0]) < 2:
                    renglones[-1][1].append(c)
                else:
                    renglones.append([c['top'], [c]])
            textos = [' '.join(''.join(c['text'] for c in sorted(cs, key=lambda c: c['x0'])).split()) for _, cs in renglones]
            salida.append((d, minuto(ya), textos))
    return salida


def mayus(linea):
    return linea.upper() == linea and re.search(r'[A-ZÁÉÍÓÚÑ]{2}', linea)


def nombre_de_ciclo(linea):
    """El ciclo de películas como se escribe, o None si no es de películas."""
    if linea.startswith('TELENOVELA'):
        return None
    if m := re.fullmatch(r'CICLO DE: (.+)', linea):
        return f'Ciclo de {m.group(1).title()}'
    return {'CINE DE ORO': 'Cine de Oro', 'PELICULA MEXICANA': 'Película mexicana'}.get(linea, linea.capitalize())


def separar(lineas):
    """(nombre tal como vino o None, programa ya armado o None, cap, título, tt, conductores, hora escrita adentro,
    si es película, su ciclo)."""
    lineas = [ENLACE.sub('', l).rstrip(' /') for l in lineas]
    lineas = [l for l in lineas if l and l not in NOTAS]
    if len(lineas) == 1 and CICLOS.match(lineas[0]):
        return SOLO_CICLO, None, None, None, None, [], None, True, nombre_de_ciclo(lineas[0])
    if m := re.fullmatch(r'REP\. ALV\. (LEYENDAS(?: \d+)?)', lineas[0]):
        lineas = ['REPORTAJES DE ALVARADO', m.group(1).capitalize()] + lineas[1:]
    nombre, resto, conductores = [], [], []
    tt = cap = inicio = None
    peli, ciclo = False, None
    for i, l in enumerate(lineas):
        if i == 0 and CICLOS.match(l):
            ciclo = nombre_de_ciclo(l)
            peli = ciclo is not None
            continue
        if l.startswith('Con ') and not mayus(l):
            conductores += re.split(r',\s*|\s+y\s+', l[4:])
            continue
        if m := re.fullmatch(r'(\d{1,2}):(\d{2}) a \d{1,2}:\d{2} hrs\.', l):
            inicio = int(m.group(1)) * 60 + int(m.group(2))
            continue
        if l == 'Canal 5' or RATING.match(l):
            continue
        partes = [p.strip() for p in l.split('/')]
        if any(p in TT for p in partes):
            for p in partes:
                if p in TT:
                    tt = TT[p]
                elif m := re.fullmatch(r'(?:[A-D]\d* )?Cap\. (\d+)', p):
                    cap = int(m.group(1))
                elif p:
                    nombre.append(p)
            continue
        if DURACION.search(l):
            peli = True
            l = DURACION.sub('', l)
            if l:
                nombre.append(l)
            continue
        # "LA PARRILLA DEL FUEGO La panza es primero": el programa y el título vienen en el mismo renglón.
        if not resto and not mayus(l) and (m := re.fullmatch(r'(.+?)\s+([A-ZÁÉÍÓÚÑ¡¿][a-záéíóúñ].*)', l)) \
                and mayus(m.group(1)):
            nombre.append(m.group(1))
            resto.append(m.group(2))
        elif mayus(l) and not resto and l not in TITULOS_EN_MAYUS:
            nombre.append(l)
        else:
            resto.append(l)
    crudo, programa = ' '.join(nombre), None
    if m := re.fullmatch(r'(.+?) (\d+)', crudo):               # LEYENDAS 01
        crudo, cap = m.group(1), int(m.group(2))
    if m := re.fullmatch(r'LAS NOTICIAS CON (.+)', crudo):
        conductores = [c.title() for c in re.split(r'\s+Y\s+', m.group(1))]
        # Hay varios "Las noticias": el primer conductor queda en el nombre para distinguirlos.
        crudo, programa = None, f'Las noticias con {conductores[0]}'.replace('Angel', 'Ángel')
    titulo = []
    for r in resto:
        if r.isdigit():
            cap = int(r)
        else:
            t = TITULOS_EN_MAYUS.get(r, r)
            titulo.append(TITULOS.get(t, t))
    conductores = [c.replace('Angel', 'Ángel') for c in conductores][:3]
    return crudo, programa, cap, ' '.join(titulo) or None, None if peli else tt, conductores, inicio, peli, ciclo


def juntar_medianoche(filas):
    """El recuadro de las 23:45 es el comienzo del programa de las 00:00 del día siguiente (a veces solo el ciclo)."""
    juntos = []
    for f in filas:
        if juntos and juntos[-1]['crudo'] in (SOLO_CICLO, f['crudo']) and f['inicio'].hour == 0 \
                and f['inicio'] - juntos[-1]['inicio'] <= dt.timedelta(minutes=15):
            juntos[-1].update(crudo=f['crudo'], datos=f['datos'], tipo=f['tipo'] or juntos[-1]['tipo'],
                              ciclo=f['ciclo'] or juntos[-1]['ciclo'])
            continue
        juntos.append(f)
    return juntos


def leer(archivos, horas_corregidas):
    filas, canales = [], set()
    for pdf in archivos:
        nombre = Path(pdf).name
        lunes = dt.datetime.strptime(re.search(r'(\d{8})-\d{8}', nombre).group(1), '%Y%m%d')
        if m := re.search(r'C-?(\d)\.?(\d)[_-]', nombre):
            canales.add(f'C-{m.group(1)}.{m.group(2)}')
        for d, desde, lineas in cajas(pdf):
            if not lineas:
                sys.exit(f'Recuadro vacío: {nombre}, día {d + 1}, minuto {desde}')
            crudo, programa, cap, titulo, tt, cond, inicio, peli, ciclo = separar(lineas)
            cond += [None] * (3 - len(cond))
            evento = crudo is not None and crudo.startswith(EVENTOS)
            filas.append({'ref': f'{nombre}, día {d + 1}', 'crudo': crudo, 'ciclo': ciclo,
                          'tipo': 'pelicula' if peli else 'evento' if evento else None,
                          'inicio': lunes + dt.timedelta(days=d, minutes=inicio if inicio is not None else desde),
                          'datos': {'TIT PRINC': programa, 'NRO CAP': cap, 'TIT CAP': titulo, 'TT': tt,
                                    'A1': cond[0], 'A2': cond[1], 'A3': cond[2]}})
    filas = juntar_medianoche(sorted(filas, key=lambda f: f['inicio']))
    if huerfanos := [f'{f["inicio"]:%d/%m %H:%M}' for f in filas if f['crudo'] == SOLO_CICLO]:
        sys.exit(f'Ciclo sin película después: {huerfanos}')
    canal = 'Televisa_Monterrey' + (f'_{canales.pop()}' if len(canales) == 1 else '')
    return {'canal': canal, 'etiqueta': 'Televisa Monterrey', 'filas': filas, 'cierre': filas[0]['inicio'] + dt.timedelta(days=7 * len(archivos))}
