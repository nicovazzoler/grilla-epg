"""ESPN ING (1A, 4A, 76A, 99A): la misma "Programming Grid" que LATAM, toda en inglés y con su propio diccionario."""
from senales import espn_latam

NOMBRE = 'ESPN ING'
ARCHIVOS = r'^(?:' + '|'.join(espn_latam.CODIGOS_ING) + r') - Programming Grid.*\.xls$'


def leer(archivos, horas_corregidas):
    return espn_latam.leer_grilla(archivos, horas_corregidas, NOMBRE)


def completar(filas):
    espn_latam.poner_compacto(filas, 'Compact - ')
    espn_latam.poner_avisos(filas)
    espn_latam.copiar_titulos(filas)
