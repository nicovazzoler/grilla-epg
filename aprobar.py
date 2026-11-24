"""Repasa los nombres nuevos de la última corrida de una señal y pasa al diccionario los aprobados.
Uso: python aprobar.py <señal> [--todo]   (--todo acepta todas las propuestas sin preguntar)"""
import json, sys
from procesar import COLUMNAS_DEL_NOMBRE, crear_patron, diccionario_de, limpiar_reparto, pendientes_de, senales

EDITABLES = [*COLUMNAS_DEL_NOMBRE, 'TIPO']

AYUDA = ('  Enter acepta · texto cambia el título · "COLUMNA=valor" cambia o borra una columna'
         f' ({", ".join(EDITABLES)}) · "p" acepta y lo usa para todo lo que empiece igual · "s" lo deja para después')


def linea(r):
    if not r.get('TIT PRINC'):
        return '(sin propuesta)'
    return '  ·  '.join([r['TIT PRINC'], *(f'{c}: {v}' for c, v in r.items() if c not in ('TIT PRINC', 'PATRON'))])


def revisar(p):
    """(reparto aprobado, si se usa como patrón), o (None, False) si queda para después."""
    r = dict(p['propuesta'])
    while True:
        print(f'  ->  {linea(r)}')
        respuesta = input('  > ').strip()
        if respuesta.lower() == 's':
            return None, False
        if not respuesta or respuesta.lower() == 'p':
            if r.get('TIT PRINC'):
                return r, respuesta.lower() == 'p'
            print('  Falta el título: escribilo o poné "s".')
        elif '=' in respuesta and (col := respuesta.split('=', 1)[0].strip()) in EDITABLES:
            valor = respuesta.split('=', 1)[1].strip()
            r = limpiar_reparto({**r, col: valor or None})
        else:
            r['TIT PRINC'] = respuesta


def para_guardar(r):
    """Si es solo el título se guarda como texto, igual que las entradas de antes."""
    r = {k: v for k, v in r.items() if k != 'PATRON'}
    return r['TIT PRINC'] if list(r) == ['TIT PRINC'] else r


if len(sys.argv) < 2 or sys.argv[1] not in senales():
    sys.exit(f'Uso: python aprobar.py <señal> [--todo]   señales: {", ".join(senales())}')
senal, todo = sys.argv[1], '--todo' in sys.argv
if not pendientes_de(senal).exists():
    sys.exit(f'No hay nada para aprobar: corré primero procesar.py {senal}')
pendientes = json.loads(pendientes_de(senal).read_text(encoding='utf-8'))
dicc_path = diccionario_de(senal)
diccionario = json.loads(dicc_path.read_text(encoding='utf-8')) if dicc_path.exists() else {}

if pendientes and not todo:
    print(AYUDA)
quedan, aprobados = [], 0
for p in pendientes:
    nota = f'  ({p["nota"]})' if p['nota'] else ''
    print(f'\n{p["crudo"]}   [{p["capa"]}]{nota}')
    if todo:
        print(f'  ->  {linea(p["propuesta"])}')
        r, patron = (p['propuesta'], p['propuesta'].get('PATRON') is True) if p['propuesta'].get('TIT PRINC') else (None, False)
    else:
        r, patron = revisar(p)
    if r is None:
        quedan.append(p)
        continue
    nuevo = crear_patron(p['crudo'], r) if patron else None
    if nuevo:
        diccionario[nuevo[0]] = nuevo[1]
        print(f'  patrón: todo lo que empiece con "{nuevo[0]}"')
    # Con un patrón que resuelve solo, el nombre exacto sobra: el patrón ya lo cubre.
    if not nuevo or nuevo[1]['RESTO']['estilo'] == 'modelo':
        diccionario[p['crudo']] = para_guardar(r)
    aprobados += 1

dicc_path.write_text(json.dumps(diccionario, ensure_ascii=False, indent=1), encoding='utf-8')
pendientes_de(senal).write_text(json.dumps(quedan, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n{aprobados} al diccionario ({len(diccionario)} nombres). Quedan {len(quedan)} sin aprobar.')
