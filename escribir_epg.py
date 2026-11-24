"""El Excel del EPG: una fila por programa, con su duración en minutos, y el control de formato de cada columna."""
import datetime as dt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
FIJAS = ['N', 'DIA', 'FECHA', 'HORA', 'DUR']
# REVISAR marca las filas con un nombre que todavía nadie aprobó.
COLUMNAS = ['TIT ORIG', 'TIT PRINC', 'CICLO', 'NRO TEMP', 'TIT TEMP', 'NRO CAP', 'TIT CAP', 'DEST', 'TT', 'DIRECTOR',
            'A1', 'A2', 'A3', 'PAIS', 'AÑO', 'SIN LARGA', 'ARG LARGO', 'DOB', 'SUB', 'SAP', 'CC', 'LS', 'GENERO',
            'TIT ING', 'TIT CAP ING', 'SIN LARGA ING', 'ARG LARGO ING',
            'TIT PORT', 'TIT CAP PORT', 'SIN LARGA PORT', 'ARG LARGO PORT', 'RATING', 'REVISAR']
# En una señal en otro idioma, su título y su capítulo ocupan el lugar de los de castellano, que pasan al final.
IDIOMAS = {
    'es': {},
    'pt': {'TIT PRINC': 'TIT PORT', 'TIT CAP': 'TIT CAP PORT', 'SIN LARGA': 'SIN LARGA PORT', 'ARG LARGO': 'ARG LARGO PORT'},
    'en': {'TIT PRINC': 'TIT ING', 'TIT CAP': 'TIT CAP ING', 'SIN LARGA': 'SIN LARGA ING', 'ARG LARGO': 'ARG LARGO ING'},
}

TEXTO_CORTO, TEXTO_LARGO = 99, 2000
LIMITES = {
    'DUR': ('entero', 720), 'NRO TEMP': ('entero', None), 'NRO CAP': ('entero', None), 'AÑO': ('año', None),
    'DEST': ('valores', {'A', 'M'}), 'TT': ('valores', {'(v)', '(d)', '(r)', '(g)'}),
    'DOB': ('valores', {1}), 'SUB': ('valores', {1}), 'SAP': ('valores', {'X'}), 'CC': ('valores', {'X'}),
    'LS': ('valores', {'X'}),
    **{c: ('texto', TEXTO_LARGO) for c in COLUMNAS if c.startswith(('SIN ', 'ARG '))},
}
ANGOSTAS = {'N': 6, 'DIA': 11, 'FECHA': 12, 'HORA': 8, 'DUR': 7, 'NRO TEMP': 9, 'TIT TEMP': 10, 'NRO CAP': 8,
            'DEST': 6, 'TT': 6, 'AÑO': 7, 'DOB': 5, 'SUB': 5, 'SAP': 5, 'CC': 5, 'LS': 5, 'REVISAR': 9}


def poner_fines(bloques, cierre):
    # Manda la hora de inicio: cada bloque dura hasta que empieza el siguiente, aunque la grilla diga otra cosa.
    for actual, siguiente in zip(bloques, bloques[1:]):
        actual['fin'] = siguiente['inicio']
    bloques[-1]['fin'] = cierre


def minutos(bloque):
    return int((bloque['fin'] - bloque['inicio']).total_seconds() // 60)


def orden(idioma):
    cambios = IDIOMAS[idioma]
    inverso = {v: k for k, v in cambios.items()}
    return [cambios.get(c) or inverso.get(c) or c for c in COLUMNAS]


def fila_de(bloque, idioma):
    """{columna: valor} con los títulos principales en las columnas del idioma de la señal."""
    datos = {IDIOMAS[idioma].get(c, c): v for c, v in bloque['datos'].items()}
    return {'DUR': minutos(bloque), **datos}


def errores_de_formato(bloques, idioma):
    """Lo que el sistema que recibe el EPG rechazaría: textos largos, valores que no existen, números que no son."""
    errores = []
    for n, b in enumerate(bloques, 1):
        for col, valor in fila_de(b, idioma).items():
            if valor in (None, '') or col == 'REVISAR':
                continue
            tipo, limite = LIMITES.get(col, ('texto', TEXTO_CORTO))
            if tipo == 'texto' and len(str(valor)) > limite:
                errores.append(f'N {n}: {col} tiene {len(str(valor))} caracteres (máx. {limite})')
            elif tipo == 'entero' and (not isinstance(valor, int) or (limite and not 0 < valor <= limite)):
                errores.append(f'N {n}: {col} = {valor!r}' + (f' (va de 1 a {limite})' if limite else ', no es un número'))
            elif tipo == 'año' and not (isinstance(valor, int) and 1000 <= valor <= 9999):
                errores.append(f'N {n}: AÑO = {valor!r}, no son 4 dígitos')
            elif tipo == 'valores' and valor not in limite:
                errores.append(f'N {n}: {col} = {valor!r}, no es uno de {sorted(map(str, limite))}')
    return errores


def guardar(bloques, canal, carpeta, idioma='es'):
    """Devuelve la ruta del Excel. Las columnas sin ningún dato no van."""
    filas = [fila_de(b, idioma) for b in bloques]
    principal = IDIOMAS[idioma].get('TIT PRINC', 'TIT PRINC')
    extra = [c for c in orden(idioma) if c == principal or any(f.get(c) not in (None, '') for f in filas)]
    cabecera = FIJAS + extra
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = 'EPG'
    hoja.append(cabecera)
    for n, (b, f) in enumerate(zip(bloques, filas), 1):
        ini = b['inicio']
        hoja.append([n, DIAS[ini.weekday()], ini.date(), ini.time(), f['DUR'], *(f.get(c) for c in extra)])

    for celda in hoja[1]:
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = PatternFill('solid', fgColor='1F4E78')
        celda.alignment = Alignment(horizontal='center')
    for fila in hoja.iter_rows(min_row=2):
        fila[2].number_format = 'dd/mm/yyyy'
        fila[3].number_format = 'hh:mm'
        for i, nombre in enumerate(cabecera):
            if nombre in ANGOSTAS:
                fila[i].alignment = Alignment(horizontal='center')
    for i, nombre in enumerate(cabecera):
        ancho = ANGOSTAS.get(nombre) or (60 if nombre.startswith(('SIN ', 'ARG ')) else 44 if nombre.startswith('TIT') else 24)
        hoja.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = ancho
    hoja.freeze_panes = 'A2'
    hoja.auto_filter.ref = hoja.dimensions

    desde, hasta = bloques[0]['inicio'], bloques[-1]['fin'] - dt.timedelta(days=1)
    salida = f'{carpeta}/{canal}_EPG_{desde:%d-%m}_al_{hasta:%d-%m}.xlsx'
    wb.save(salida)
    return salida
