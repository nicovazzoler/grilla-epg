"""Repasa los nombres nuevos de la última corrida y pasa al diccionario los aprobados.
Uso: python aprobar.py [--todo]   (--todo acepta todas las propuestas sin preguntar)"""
import json, sys
from procesar import DICCIONARIO, PENDIENTES

if not PENDIENTES.exists():
    sys.exit('No hay nada para aprobar: corré primero procesar.py')
pendientes = json.loads(PENDIENTES.read_text(encoding='utf-8'))
diccionario = json.loads(DICCIONARIO.read_text(encoding='utf-8')) if DICCIONARIO.exists() else {}
todo = '--todo' in sys.argv

quedan, aprobados = [], 0
for p in pendientes:
    nota = f'  ({p["nota"]})' if p['nota'] else ''
    print(f'\n{p["crudo"]}  ->  {p["propuesta"] or "(sin propuesta)"}   [{p["capa"]}]{nota}')
    if todo:
        respuesta = '' if p['propuesta'] else 's'
    else:
        respuesta = input('  Enter acepta, escribí el nombre correcto, o "s" para dejarlo para después: ').strip()
    if respuesta.lower() == 's' or (not respuesta and not p['propuesta']):
        quedan.append(p)
        continue
    diccionario[p['crudo']] = respuesta or p['propuesta']
    aprobados += 1

DICCIONARIO.write_text(json.dumps(diccionario, ensure_ascii=False, indent=1), encoding='utf-8')
PENDIENTES.write_text(json.dumps(quedan, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n{aprobados} al diccionario ({len(diccionario)} nombres). Quedan {len(quedan)} sin aprobar.')
