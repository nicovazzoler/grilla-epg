"""El Excel del EPG: una fila por programa, con su duración en minutos."""
import datetime as dt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
COLUMNAS = ['Programa', 'Año', 'Cap.', 'TT']
ANCHOS = {'N': 6, 'Día': 11, 'Fecha': 12, 'Hora': 8, 'Duración': 10, 'Programa': 44, 'Año': 7, 'Cap.': 6, 'TT': 6}
CENTRADAS = {'N', 'Fecha', 'Hora', 'Duración', 'Año', 'Cap.', 'TT'}


def poner_fines(bloques):
    # Manda la hora de inicio: cada bloque dura hasta que empieza el siguiente, y la semana cierra a los 7 días.
    for actual, siguiente in zip(bloques, bloques[1:]):
        actual['fin'] = siguiente['inicio']
    bloques[-1]['fin'] = bloques[0]['inicio'] + dt.timedelta(days=7)


def minutos(bloque):
    return int((bloque['fin'] - bloque['inicio']).total_seconds() // 60)


def guardar(bloques, canal, carpeta):
    """Devuelve la ruta del Excel. Las columnas sin ningún dato no van."""
    extra = [c for c in COLUMNAS if c == 'Programa' or any(b['datos'].get(c) not in (None, '') for b in bloques)]
    cabecera = ['N', 'Día', 'Fecha', 'Hora', 'Duración', *extra]
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = 'EPG'
    hoja.append(cabecera)
    for n, b in enumerate(bloques, 1):
        ini = b['inicio']
        hoja.append([n, DIAS[ini.weekday()], ini.date(), ini.time(), minutos(b), *(b['datos'].get(c) for c in extra)])

    for celda in hoja[1]:
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = PatternFill('solid', fgColor='1F4E78')
        celda.alignment = Alignment(horizontal='center')
    for fila in hoja.iter_rows(min_row=2):
        fila[2].number_format = 'dd/mm/yyyy'
        fila[3].number_format = 'hh:mm'
        for i, nombre in enumerate(cabecera):
            if nombre in CENTRADAS:
                fila[i].alignment = Alignment(horizontal='center')
    for i, nombre in enumerate(cabecera):
        hoja.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = ANCHOS[nombre]
    hoja.freeze_panes = 'A2'
    hoja.auto_filter.ref = hoja.dimensions

    desde, hasta = bloques[0]['inicio'], bloques[-1]['fin'] - dt.timedelta(days=1)
    salida = f'{carpeta}/{canal}_EPG_{desde:%d-%m}_al_{hasta:%d-%m}.xlsx'
    wb.save(salida)
    return salida
