"""América TV (Perú): grilla semanal en .xls, una columna por día y un recuadro con bordes por programa.
El programa empieza en el borde de arriba del recuadro, esté donde esté escrito el nombre."""
import datetime as dt
import re
import xlrd

MESES = {'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
         'SETIEMBRE': 9, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12}
# Columna principal de cada día: una celda combinada vale para un día si pisa esa columna.
DIAS = {4: 0, 6: 1, 8: 2, 10: 3, 12: 4, 14: 5, 15: 6}
DIAS_NOMBRE = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
FILA_0, FILA_N, COL_HORA = 7, 85, 2
CORTE = 5 * 60 + 16          # el día de la grilla arranca 05:16
CICLOS = {'*MATINEE DE AMERICA*': 'Matinée de América', '*BUTACA AMERICA*': 'Butaca América'}
ROTULOS = {'*SERIE*', '*DOCUMENTAL*'}
# Los actores vienen sueltos dentro del recuadro de la película y no van.
ACTORES = {'ANTONIO BANDERAS', 'DWAYNE JOHNSON', 'JONATHAN PRYCE', 'JUSTIN LONG', 'MARTA GONZALEZ DE VEGA',
           'MATTHEW GRAY GUBLER', 'MELANIA URBINA', 'ROBERT DOWNEY JR,', 'VALIN SHINYEI'}


class Grilla:
    def __init__(self, archivo):
        self.libro = xlrd.open_workbook(archivo, formatting_info=True)
        self.hoja = self.libro.sheet_by_index(0)
        self.combinadas = [(r0, r1 - 1, c0, c1 - 1) for r0, r1, c0, c1 in self.hoja.merged_cells]

    def lunes(self):
        titulo = ' '.join(str(self.hoja.cell_value(r, c)) for r in range(4) for c in range(self.hoja.ncols))
        m = re.search(r'DEL (\d{1,2}) AL \d{1,2} DE (\w+) DEL (\d{4})', titulo)
        return dt.datetime(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))

    def hora(self, fila):
        """Minutos desde las 00:00 de la hora de la fila, o de la celda combinada de hora que la cubre."""
        for r0, r1, c0, c1 in self.combinadas:
            if c0 <= COL_HORA <= c1 and r0 <= fila <= r1:
                fila = r0
        v = self.hoja.cell_value(fila, COL_HORA)
        if isinstance(v, str):
            h, m = map(int, v.split(':'))
            return h * 60 + m
        return round(v * 1440)

    def bordes(self, col):
        """Filas donde arranca un recuadro en la columna del día."""
        def arriba(r):
            xf = self.libro.xf_list
            return (xf[self.hoja.cell_xf_index(r, col)].border.top_line_style > 0
                    or xf[self.hoja.cell_xf_index(r - 1, col)].border.bottom_line_style > 0)
        return [r for r in range(FILA_0, FILA_N + 2) if arriba(r)]

    def celdas(self, col):
        """(fila inicial, texto) de cada celda con texto que vale para la columna del día."""
        vistas, salida = set(), []
        for r0, r1, c0, c1 in self.combinadas:
            if c0 <= col <= c1 and FILA_0 <= r0 <= FILA_N:
                vistas.update(range(r0, r1 + 1))
                salida.append((r0, self.hoja.cell_value(r0, c0)))
        for r in range(FILA_0, FILA_N + 1):
            if r not in vistas:
                salida.append((r, self.hoja.cell_value(r, col)))
        return sorted((r, ' '.join(str(t).split())) for r, t in salida if str(t).strip())


def limpiar(texto):
    """(nombre tal como vino, temporada, tt)."""
    t = texto.replace('"', '').strip()
    tt = None
    if t.endswith('(REPETICION)'):
        tt, t = '(r)', t[:-len('(REPETICION)')].strip()
    t = re.sub(r'^TN\. ?', '', t)
    temp = None
    if m := re.search(r'\s*\((\d+)° TEMPORADA\)$', t):
        temp, t = int(m.group(1)), t[:m.start()]
    t = re.sub(r'\s*\(Temporada \d+\)$', '', t)
    return t, temp, tt


def leer(archivos, horas_corregidas):
    filas = []
    for archivo in archivos:
        g = Grilla(archivo)
        lunes = g.lunes()
        for col, n_dia in DIAS.items():
            dia = lunes + dt.timedelta(days=n_dia)
            tops = g.bordes(col)
            recuadros = {}
            for fila, texto in g.celdas(col):
                if texto not in ACTORES:
                    recuadros.setdefault(max(t for t in tops if t <= fila), []).append(texto)
            for top, textos in sorted(recuadros.items()):
                ciclo = next((CICLOS[t] for t in textos if t in CICLOS), None)
                crudo, temp, tt = limpiar(' '.join(t for t in textos if t not in CICLOS and t not in ROTULOS))
                minutos = g.hora(top)
                inicio = dia + dt.timedelta(days=1 if minutos < CORTE else 0, minutes=minutos)
                fila = {'ref': f'{DIAS_NOMBRE[n_dia]}, fila {top + 1}', 'inicio': inicio, 'crudo': crudo,
                        'datos': {'CICLO': ciclo, 'NRO TEMP': temp, 'TT': tt}}
                # La 05:00 del final de un día y la 05:16 del principio del siguiente son el mismo programa.
                if filas and (filas[-1]['crudo'], filas[-1]['datos']) == (crudo, fila['datos']):
                    continue
                filas.append(fila)
    return {'canal': 'America_TV', 'filas': filas,
            'cierre': filas[0]['inicio'].replace(hour=0, minute=0) + dt.timedelta(days=7 * len(archivos), minutes=CORTE)}

