"""Canal 51: un .docx por semana, con el día en su propia línea y debajo "HH:MMAM: programa"."""
import datetime as dt
import re
import docx

MESES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
         'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
CINE = re.compile(r'cine (5 ?-?1?|51 ?[–-] ?[123]|51-[123]|51|clasico)', re.I)
OTROS_CICLOS = re.compile(r'^(documental rt|musica en vivo|desde china):\s*', re.I)
ANIO = re.compile(r'^(.+) ((?:19|20)\d\d)$')


def hora(texto):
    """'06:30AM', '2:00PM' o '12:00MD' a datetime.time."""
    h, m, sufijo = re.fullmatch(r'(\d{1,2}):(\d{2})(AM|PM|MD)', texto).groups()
    h, m = int(h), int(m)
    if sufijo == 'PM' and h != 12:
        h += 12
    if sufijo == 'AM' and h == 12:
        h = 0
    return dt.time(h, m)


def fecha(dia, mes):
    # El .docx no trae el año: se toma el de hoy, salvo que la fecha quede a más de medio año (cruce de año).
    hoy = dt.date.today()
    d = dt.datetime(hoy.year, mes, dia)
    if (hoy - d.date()).days > 180:
        d = d.replace(year=hoy.year + 1)
    return d


def separar(texto):
    """(nombre tal como vino, año, cap, si es película, si es repetición)."""
    t = ' '.join(texto.split())
    repriss = bool(re.search(r'repriss', t, re.I))
    if m := CINE.match(t):
        resto = t[m.end():]
        titulo = re.sub(r'^.*?:\s*', '', resto, count=1).lower().strip() if ':' in resto else ''
        anio = None
        if a := ANIO.match(titulo):
            titulo, anio = a.group(1), int(a.group(2))
        return titulo, anio, None, True, repriss
    t = OTROS_CICLOS.sub('', t)
    t = re.sub(r'\s*repriss\s*', ' ', t, flags=re.I).strip()
    if m := re.fullmatch(r'El valor de la Familia (\d+)', t):
        return 'el valor de la familia', None, int(m.group(1)), False, repriss
    return t.lower(), None, None, False, repriss


def leer(archivos, horas_corregidas):
    filas = []
    for semana, archivo in enumerate(archivos):
        dia = None
        for n, p in enumerate(docx.Document(archivo).paragraphs):
            linea = p.text.strip()
            if m := re.fullmatch(r'\w+ (\d{1,2}) de (\w+)', linea):
                dia = fecha(int(m.group(1)), MESES[m.group(2).lower()])
                continue
            if not (m := re.fullmatch(r'(\d{1,2}:\d{2}(?:AM|PM|MD)):\s*(.+)', linea)):
                continue
            h = hora(m.group(1))
            # El día de la grilla va de 06:00 a 06:00: la madrugada es del día calendario siguiente.
            inicio = dt.datetime.combine(dia.date(), h) + dt.timedelta(days=1 if h.hour < 6 else 0)
            crudo, anio_peli, cap, peli, repriss = separar(m.group(2))
            filas.append({'ref': f'semana {semana + 1}, línea {n + 1}', 'inicio': inicio, 'crudo': crudo,
                          'semana': semana, 'peli': peli, 'repriss': repriss,
                          # Las películas no llevan TT.
                          'datos': {'AÑO': anio_peli, 'NRO CAP': cap, 'TT': '(r)' if repriss and not peli else None}})
    return {'canal': 'Canal_51', 'filas': filas, 'cierre': filas[0]['inicio'] + dt.timedelta(days=7 * len(archivos))}


def completar(bloques):
    # Estreno (A) solo la primera vez que pasa cada película en la semana, y nunca en una repetición.
    vistas = set()
    for b in bloques:
        if not b['peli']:
            continue
        clave = (b['semana'], b['datos']['TIT PRINC'])
        if not b['repriss'] and clave not in vistas:
            b['datos']['DEST'] = 'A'
        vistas.add(clave)
