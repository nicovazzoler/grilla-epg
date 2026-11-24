"""RBTV (Rede Brasil): grade semanal en Excel, una fila de fecha y debajo hora y programa."""
import datetime as dt
import re
import openpyxl

CICLO = re.compile(r'^([^:]+): (.+)$')
INFOMERCIAL = re.compile(r'INFOMERCIAL \d+ MINUTOS')


def limpiar(texto):
    """(nombre tal como vino, año, capítulo, TT, ciclo)."""
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
        return 'INFOMERCIAL', None, None, tt, None
    t = re.sub(r'^PROGRAMA:\s*', '', t)
    cap = ciclo = None
    if m := re.fullmatch(r'EM REVISTA: PGM (\d+)', t):
        t, cap = 'EM REVISTA', int(m.group(1))
    elif m := CICLO.match(t):
        ciclo, t = ' '.join(m.group(1).split()), m.group(2)
    return t, anio, cap, tt, ciclo


def leer(archivos, horas_corregidas):
    filas, fecha = [], None
    for archivo in archivos:
        hoja = openpyxl.load_workbook(archivo).worksheets[0]
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
            crudo, anio, cap, tt, ciclo = limpiar(str(prog))
            # Los ciclos de la grade son casi todos de series: es película si trae año o el ciclo es de cine.
            peli = anio is not None or bool(ciclo and 'CINE' in ciclo)
            filas.append({'ref': f'fila {fila}', 'inicio': inicio, 'crudo': crudo,
                          'tipo': 'pelicula' if peli else None, 'ciclo': ciclo.capitalize() if peli and ciclo else None,
                          'datos': {'AÑO': anio, 'NRO CAP': cap, 'TT': tt}})
    return {'canal': 'RBTV', 'etiqueta': 'RBTV', 'idioma': 'pt', 'filas': filas, 'cierre': filas[0]['inicio'] + dt.timedelta(days=7 * len(archivos))}
