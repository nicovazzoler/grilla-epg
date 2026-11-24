"""Grilla semanal: la última semana se repite hasta el fin del mes en que termina la grilla.
En los días repetidos las películas pasan a su ciclo (o "Película") y los eventos al nombre de la señal,
sin ningún otro dato; el resto queda igual pero sin capítulo."""
import datetime as dt

SIN_CAPITULO = ('NRO CAP', 'TIT CAP')
# Los títulos que, si la señal los trae, no pueden quedar vacíos: en un ciclo o evento llevan lo mismo que TIT PRINC.
OTROS_TITULOS = ('TIT ORIG', 'TIT ING', 'TIT PORT')


def mes_siguiente(cierre):
    """Las 00:00 del 1° del mes que sigue al último día de la grilla: desde ahí no puede empezar ningún programa."""
    ultimo = cierre - dt.timedelta(days=1)
    return dt.datetime.combine((ultimo.replace(day=28) + dt.timedelta(days=4)).replace(day=1), dt.time())


def repetido(fila, etiqueta):
    """La fila como va en un día repetido."""
    tipo = fila.get('tipo')
    if tipo not in ('pelicula', 'evento'):
        return {**fila, 'datos': {c: v for c, v in fila['datos'].items() if c not in SIN_CAPITULO}}
    nombre = (fila.get('ciclo') or 'Película') if tipo == 'pelicula' else etiqueta
    datos = {'TIT PRINC': nombre, **{c: nombre for c in OTROS_TITULOS if fila['datos'].get(c)}}
    return {**fila, 'datos': datos}


def estirar(filas, cierre, etiqueta):
    """(filas con las semanas repetidas, nuevo cierre).
    No entra nada que empiece en el mes siguiente; el último programa dura hasta donde empezaría el próximo."""
    limite = mes_siguiente(cierre)
    if filas[-1]['inicio'] >= limite:
        return filas, cierre
    semana = [f for f in filas if f['inicio'] >= cierre - dt.timedelta(days=7)]
    nuevas, vuelta = list(filas), 1
    while True:
        for f in semana:
            inicio = f['inicio'] + dt.timedelta(days=7 * vuelta)
            if inicio >= limite:
                return nuevas, inicio
            nuevas.append({**repetido(f, etiqueta), 'inicio': inicio})
        vuelta += 1
