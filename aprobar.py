"""Repasa los nombres nuevos de la última corrida de una señal y pasa al diccionario los aprobados.
Uso: python aprobar.py <señal> [--todo]   (--todo acepta todas las propuestas sin preguntar)"""
import json, sys
from procesar import diccionario_de, pendientes_de, senales

if len(sys.argv) < 2 or sys.argv[1] not in senales():
    sys.exit(f'Uso: python aprobar.py <señal> [--todo]   señales: {", ".join(senales())}')
senal, todo = sys.argv[1], '--todo' in sys.argv
if not pendientes_de(senal).exists():
    sys.exit(f'No hay nada para aprobar: corré primero procesar.py {senal}')
pendientes = json.loads(pendientes_de(senal).read_text(encoding='utf-8'))
dicc_path = diccionario_de(senal)
diccionario = json.loads(dicc_path.read_text(encoding='utf-8')) if dicc_path.exists() else {}

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

dicc_path.write_text(json.dumps(diccionario, ensure_ascii=False, indent=1), encoding='utf-8')
pendientes_de(senal).write_text(json.dumps(quedan, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n{aprobados} al diccionario ({len(diccionario)} nombres). Quedan {len(quedan)} sin aprobar.')
