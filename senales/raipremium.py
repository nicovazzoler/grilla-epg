"""Rai Premium: la guía de RaiPlay, un JSON por día con la hora de Italia y la temporada y el capítulo separados.
Se baja con `python procesar.py raipremium --desde 28/11 --hasta 02/12` o se leen JSON ya guardados."""
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

NOMBRE = 'Rai Premium'
ARCHIVOS = r'raipremium_\d{4}-\d{2}-\d{2}\.json$'
FEED = 'https://www.raiplay.it/palinsesto/app/rai-premium/{:%d-%m-%Y}.json'


def descargar(desde, hasta, carpeta):
    rutas, dia = [], desde
    while dia <= hasta:
        with urllib.request.urlopen(FEED.format(dia), timeout=30) as r:
            datos = json.load(r)
        if datos.get('events'):
            ruta = Path(carpeta) / f'raipremium_{dia:%Y-%m-%d}.json'
            ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
            rutas.append(str(ruta))
        dia += dt.timedelta(days=1)
    return rutas


def temporada(valor):
    """{columna: valor} de lo que RaiPlay pone en "season": un número, un año ("1999") o un ciclo anual ("2026/27")."""
    v = (valor or '').strip()
    if re.fullmatch(r'(19|20)\d\d', v):
        return {'AÑO': int(v)}
    if v.isdigit():
        return {'NRO TEMP': int(v)}
    return {'TIT TEMP': v} if v else {}


def fila(ev, n, archivo):
    inicio = dt.datetime.strptime(f'{ev["date"]} {ev["hour"]}', '%d/%m/%Y %H:%M')
    programa = ((ev.get('program') or {}).get('name') or ev['name']).strip()
    cap = (ev.get('episode_title') or '').strip()
    nro = int(ev['episode']) if str(ev.get('episode') or '').isdigit() else None
    # "Episodio 64" no agrega nada que no diga NRO CAP.
    if re.fullmatch(r'Episodio \d+', cap):
        cap = ''
    datos = {'NRO CAP': nro, 'TIT CAP': cap or None, 'ARG LARGO': ' '.join((ev.get('description') or '').split()) or None,
             **temporada(ev.get('season'))}
    # Un año con capítulo es el de la temporada ("Blu Notte", 1999, cap. 4): no la hace película.
    pelicula = not nro and not cap and ('AÑO' in datos or (not ev.get('season')
                                                          and int(ev['duration'].split(':')[0]) >= 1))
    h, m, _ = map(int, ev['duration'].split(':'))
    return {'ref': f'{Path(archivo).name}, programa {n}', 'inicio': inicio, 'crudo': ' '.join(programa.split()),
            'tipo': 'pelicula' if pelicula else None, 'ciclo': None, 'datos': datos,
            'serie': bool(nro or cap or (ev.get('season') and 'AÑO' not in datos)),
            'fin_guia': inicio + dt.timedelta(hours=h, minutes=m)}


def leer(archivos, horas_corregidas):
    filas = []
    for archivo in sorted(archivos):
        eventos = json.loads(Path(archivo).read_text(encoding='utf-8'))['events']
        filas += [fila(ev, n, archivo) for n, ev in enumerate(eventos, 1)]
    if not filas:
        raise SystemExit('No hay programas: RaiPlay no publicó esos días todavía.')
    filas.sort(key=lambda f: f['inicio'])
    # La guía a veces no trae la temporada de una serie: si en otro día la trae, no es película.
    series = {f['crudo'] for f in filas if f['serie']}
    for f in filas:
        if f['crudo'] in series:
            f['tipo'] = None
    # El último programa trae su duración: termina cuando dice la guía, aunque sea pasada la medianoche.
    return {'canal': 'Rai_Premium', 'etiqueta': NOMBRE, 'idioma': 'es', 'filas': filas, 'cierre': filas[-1]['fin_guia']}
