"""Corre cada grilla de referencia y compara el EPG contra el que ya se sabe que está bien.
Es para antes de un PR que toque un lector o el armado: si algo se movió sin querer, lo dice.

Cada caso es una carpeta referencias/<señal>/<caso>/ con las grillas, esperado.xlsx y, si hace falta,
opciones.json ({"semanal": true, "horas": {"288": "20:30"}}).
Uso: python probar.py [señal]"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
import openpyxl
from escribir_epg import IDIOMAS
from procesar import COLUMNAS_DEL_NOMBRE, armar, guardar, leer_grillas

REFERENCIAS = Path(__file__).parent / 'referencias'


def leer_excel(ruta):
    hoja = openpyxl.load_workbook(ruta).active
    cabecera = [c.value for c in hoja[1]]
    return [dict(zip(cabecera, (c.value for c in fila))) for fila in hoja.iter_rows(min_row=2)]


def repartos_del_esperado(leido, esperado):
    """Los nombres salen del EPG esperado, fila por fila: la prueba es del lector y del armado, no del diccionario.
    Una columna del nombre que el lector dejó vacía y el esperado trae vino del diccionario."""
    principal = IDIOMAS[leido.get('idioma', 'es')].get('TIT PRINC', 'TIT PRINC')
    capitulo = IDIOMAS[leido.get('idioma', 'es')].get('TIT CAP', 'TIT CAP')
    repartos = {}
    for fila, bueno in zip(leido['filas'], esperado):
        if fila['crudo'] is None or fila['crudo'] in repartos:
            continue
        r = {'TIT PRINC': bueno.get(principal)}
        for col in COLUMNAS_DEL_NOMBRE:
            columna_excel = capitulo if col == 'TIT CAP' else col
            if fila['datos'].get(col) in (None, '') and bueno.get(columna_excel) not in (None, ''):
                r[col] = bueno[columna_excel]
        repartos[fila['crudo']] = r
    return repartos


def probar(caso):
    """Lista de diferencias entre lo que sale hoy y esperado.xlsx; vacía si da igual."""
    senal = caso.parent.name
    opciones = json.loads((caso / 'opciones.json').read_text(encoding='utf-8')) if (caso / 'opciones.json').exists() else {}
    horas = {int(f): dt.datetime.strptime(h, '%H:%M').time() for f, h in opciones.get('horas', {}).items()}
    grillas = sorted(str(p) for p in caso.iterdir() if p.name not in ('esperado.xlsx', 'opciones.json'))
    esperado = leer_excel(caso / 'esperado.xlsx')

    leido = leer_grillas(senal, grillas, horas)
    repartos = repartos_del_esperado(leido, esperado)
    filas, _ = armar(senal, leido, repartos, set(), opciones.get('semanal', False))
    with tempfile.TemporaryDirectory() as carpeta:
        obtenido = leer_excel(guardar(filas, leido['canal'], carpeta, leido.get('idioma', 'es')))

    diferencias = []
    if len(obtenido) != len(esperado):
        diferencias.append(f'{len(obtenido)} filas, se esperaban {len(esperado)}')
    for n, (hoy, bueno) in enumerate(zip(obtenido, esperado), 1):
        for col in sorted(set(hoy) | set(bueno)):
            if hoy.get(col) != bueno.get(col):
                diferencias.append(f'N {n}, {col}: sale {hoy.get(col)!r}, se esperaba {bueno.get(col)!r}')
    return diferencias


def main():
    casos = sorted(c for c in REFERENCIAS.glob('*/*') if c.is_dir() and (c / 'esperado.xlsx').exists())
    if len(sys.argv) > 1:
        casos = [c for c in casos if c.parent.name == sys.argv[1]]
    if not casos:
        sys.exit(f'No hay casos en {REFERENCIAS}/<señal>/<caso>/ (cada uno con sus grillas y esperado.xlsx).')
    fallaron = 0
    for caso in casos:
        try:
            diferencias = probar(caso)
        except (Exception, SystemExit) as e:
            diferencias = [f'no se pudo correr: {e}']
        estado = 'ok' if not diferencias else f'{len(diferencias)} diferencias'
        print(f'{caso.parent.name}/{caso.name}: {estado}')
        for d in diferencias[:8]:
            print(f'    {d}')
        fallaron += bool(diferencias)
    print(f'\n{len(casos) - fallaron} de {len(casos)} iguales')
    sys.exit(1 if fallaron else 0)


if __name__ == '__main__':
    main()
