"""Claro Sports: un Excel en lista, una fila por programa con fecha, hora, aire, rating y sinopsis."""
import datetime as dt
import re
from pathlib import Path
import openpyxl

NOMBRE = 'Claro Sports'
ARCHIVOS = r'claro.?sports.*\.xlsx$'
FEEDS = {'SUDAMERICA': 'Sudamerica', 'MEXICO': 'Mexico', 'CENTROAMERICA': 'Centroamerica'}
TT = {'VIVO': '(v)', 'DIFERIDO': '(d)'}
# Lo que viene con el partido o la etapa pegados: lo de adelante va al diccionario y el resto, a TIT CAP.
# Sin separador no se puede saber dónde termina el torneo, así que cada uno nuevo se suma acá.
TORNEOS = ('SUPER LIGA DE GRECIA', 'COPA DE GRECIA', 'WTGL', 'CEV CHAMPIONS LEAGUE VOLLEY WOMEN',
           'CEV CL VOLLEY WOMEN', 'HL UCI BMX FREESTYLE WORLD CUP', 'HL FEI WESTERN EUROPEAN LEAGUE')
CON_CAPITULO = ('JUGANDO CLARO',)
SIGLAS = {'MX': 'MX', 'BBVA': 'BBVA', 'SC': 'SC', 'DOC': 'DOC', 'AEK': 'AEK', 'VFB': 'VfB', 'VS': 'vs.'}
# Solo estas: 'Los Angeles' o 'El Salvador' son nombres de equipos.
CHICAS = {'de', 'del'}


def limpio(texto):
    return ' '.join(str(texto or '').replace('\xa0', ' ').split())


def titulo(texto):
    """Un partido o una etapa escritos como nombres propios: 'Olympiacos vs. AEK'."""
    palabras = texto.split()
    return ' '.join(SIGLAS.get(p, p.lower() if i and p.lower() in CHICAS else p[:1] + p[1:].lower())
                    for i, p in enumerate(palabras))


def separar(nombre):
    """(nombre para el diccionario, capítulo, si es un evento)."""
    for prefijo in sorted(TORNEOS + CON_CAPITULO, key=len, reverse=True):
        if nombre.startswith(prefijo + ' '):
            return prefijo, titulo(nombre[len(prefijo) + 1:]), prefijo in TORNEOS
    return nombre, None, False


def fecha(valor, anterior):
    """La grilla escribe mes/día y Excel la lee como día/mes cuando puede: 12/01 queda 12 de enero.
    De las dos lecturas, la que sigue a la fecha de la fila anterior."""
    if isinstance(valor, str):
        return dt.datetime.strptime(valor.strip(), '%m/%d/%Y').date()
    d = valor.date()
    opciones = [dt.date(d.year, d.day, d.month)] if d.day <= 12 else []
    opciones.append(d)
    if anterior is None:
        return opciones[0]
    return min(opciones, key=lambda o: abs((o - anterior).days))


def feed(archivo):
    nombre = Path(archivo).name.upper()
    return next((v for k, v in FEEDS.items() if k in nombre), None)


def leer(archivos, horas_corregidas):
    filas, dia, fin = [], None, None
    for archivo in archivos:
        hoja = openpyxl.load_workbook(archivo, data_only=True).active
        for n, (f, hora, termina, _, nombre, aire, rating, sinopsis) in enumerate(
                hoja.iter_rows(min_row=2, max_col=8, values_only=True), 2):
            nombre = limpio(nombre).upper()
            if not nombre or hora is None:
                continue
            dia = fecha(f, dia)
            hora = horas_corregidas.get(n, hora)
            inicio = dt.datetime.combine(dia, hora)
            fin = dt.datetime.combine(dia, termina) + dt.timedelta(days=1 if termina <= hora else 0)
            # Los fillers no van: el programa de antes sigue hasta que empieza el siguiente.
            if nombre.startswith('FILLER'):
                continue
            crudo, cap, evento = separar(nombre)
            filas.append({'ref': f'fila {n}', 'inicio': inicio, 'crudo': crudo,
                          'tipo': 'evento' if evento else None, 'ciclo': None,
                          'datos': {'TIT CAP': cap, 'TT': TT.get(limpio(aire).upper()),
                                    'RATING': limpio(rating) or None, 'SIN LARGA': limpio(sinopsis) or None}})
    canal = '_'.join(filter(None, ['Claro_Sports', feed(archivos[0])]))
    return {'canal': canal, 'etiqueta': NOMBRE, 'filas': filas, 'cierre': fin}
