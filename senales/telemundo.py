"""Telemundo: no manda grilla, la publica en su guía web. Un JSON por día, con la hora del Este de EE. UU.
Se baja con `python procesar.py telemundo --desde 28/11 --hasta 03/12` o se leen JSON ya guardados."""
import datetime as dt
import json
import urllib.request
from pathlib import Path

NOMBRE = 'Telemundo'
ARCHIVOS = r'block_\d{4}-\d{2}-\d{2}\.json$'
FEED = 'https://d3ur398j0yj7gx.cloudfront.net/ajax/program_guide/feed/block/{:%Y/%m/%d}'


def descargar(desde, hasta, carpeta):
    """Baja un JSON por día, de desde a hasta inclusive. Los días que la guía todavía no publicó no se guardan."""
    rutas, dia = [], desde
    while dia <= hasta:
        with urllib.request.urlopen(FEED.format(dia), timeout=30) as r:
            cuerpo = r.read()
        if cuerpo.strip():
            ruta = Path(carpeta) / f'block_{dia:%Y-%m-%d}.json'
            ruta.write_bytes(cuerpo)
            rutas.append(str(ruta))
        dia += dt.timedelta(days=1)
    return rutas


def leer(archivos, horas_corregidas):
    filas = []
    for archivo in sorted(archivos):
        for n, p in enumerate(json.loads(Path(archivo).read_text(encoding='utf-8')), 1):
            dia = dt.datetime.strptime(p['date'].split()[0], '%Y/%m/%d')
            # "time" viene redondeado a la hora ("12am"); "time_full" trae los minutos ("12:05am").
            hora = dt.datetime.strptime(p['time_full'].upper(), '%I:%M%p').time()
            filas.append({'ref': f'{Path(archivo).name}, programa {n}', 'inicio': dt.datetime.combine(dia.date(), hora),
                          'crudo': ' '.join(p['name'].split()), 'tipo': None, 'ciclo': None,
                          'datos': {'ARG LARGO': ' '.join((p.get('description') or '').split()) or None,
                                    'RATING': p.get('rating')}})
    if not filas:
        raise SystemExit('No hay programas: la guía de Telemundo no publicó esos días todavía.')
    filas.sort(key=lambda f: f['inicio'])
    # El último día termina a la medianoche del Este: el feed no dice cuánto dura el último programa.
    cierre = dt.datetime.combine(filas[-1]['inicio'].date() + dt.timedelta(days=1), dt.time())
    return {'canal': 'Telemundo', 'etiqueta': NOMBRE, 'idioma': 'es', 'filas': filas, 'cierre': cierre}
