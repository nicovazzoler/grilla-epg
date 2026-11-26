"""ESPN ING (1A, 4A, 76A, 99A): la misma "Programming Grid" que LATAM, toda en inglés y con su propio diccionario."""
from senales import espn_latam

NOMBRE = 'ESPN ING'
ARCHIVOS = r'^(?:' + '|'.join(espn_latam.CODIGOS_ING) + r') - Programming Grid.*\.xls$'


def leer(archivos, horas_corregidas):
    # "Compacto" es una palabra de los EPG en castellano: acá un partido corto queda con su nombre.
    return espn_latam.leer_grilla(archivos, horas_corregidas, NOMBRE, compactos=False)


def completar(filas):
    espn_latam.copiar_titulos(filas)
