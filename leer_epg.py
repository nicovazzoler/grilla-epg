"""El EPG de salida/ en texto, para leerlo o revisarlo sin abrir Excel.

Solo biblioteca estándar: anda igual en WSL que en Windows, con openpyxl instalado o sin él.
Por qué existe: el único lugar donde se ve lo que se le va a mandar a la señal es el Excel, y
revisarlo a ojo en una planilla de 500 filas es cómo se mandan los errores.

  python leer_epg.py salida/RBTV_EPG_16-11_al_22-11.xlsx              # todas las filas
  python leer_epg.py salida/RBTV_EPG_16-11_al_22-11.xlsx --resumen    # totales y lo que llama la atención
  python leer_epg.py ... --resumen --corto 10 --largo 240             # los límites de "duración rara"
"""
import argparse, datetime as dt, re, sys, unicodedata, zipfile
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
EPOCA = dt.datetime(1899, 12, 30)   # el día 1 de Excel es el 31/12/1899
# Las que escribir_epg.py puede llegar a poner: una que falte puede ser que la señal no la use
# esta semana, o que un regex del lector dejó de andar.
POSIBLES = ['N', 'Día', 'Fecha', 'Hora', 'Duración', 'Programa', 'Ciclo', 'Temp.', 'Año', 'Cap.',
            'Título', 'TT', 'DEST', 'A1', 'A2', 'A3']


def columna(ref):
    """'AB12' -> 27, contando desde 0."""
    n = 0
    for letra in re.match(r'[A-Z]+', ref).group():
        n = n * 26 + ord(letra) - 64
    return n - 1


def filas_crudas(xlsx):
    with zipfile.ZipFile(xlsx) as z:
        cadenas = []
        if 'xl/sharedStrings.xml' in z.namelist():
            cadenas = [''.join(t.text or '' for t in si.iter(f'{NS}t'))
                       for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        hojas = sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n))
        raiz = ET.fromstring(z.read(hojas[0]))
    for fila in raiz.iter(f'{NS}row'):
        celdas = {}
        for c in fila.findall(f'{NS}c'):
            v = c.find(f'{NS}v')
            if c.get('t') == 's':
                valor = cadenas[int(v.text)] if v is not None else None
            elif c.get('t') in ('inlineStr', 'str'):
                valor = ''.join(t.text or '' for t in c.iter(f'{NS}t')) or None
            elif v is None or v.text is None:
                valor = None
            else:
                valor = float(v.text) if re.search(r'[.eE]', v.text) else int(v.text)
            celdas[columna(c.get('r'))] = valor
        yield [celdas.get(i) for i in range(max(celdas, default=-1) + 1)]


def leer(xlsx):
    """(cabecera, filas como dict) con Fecha y Hora ya convertidas."""
    it = filas_crudas(xlsx)
    cabecera = [str(c) for c in next(it) if c is not None]
    filas = []
    for f in it:
        d = dict(zip(cabecera, f + [None] * (len(cabecera) - len(f))))
        if d.get('Fecha') is not None:
            d['Fecha'] = (EPOCA + dt.timedelta(days=float(d['Fecha']))).date()
        if d.get('Hora') is not None:
            m = round(float(d['Hora']) % 1 * 1440)
            d['Hora'] = dt.time(m // 60 % 24, m % 60)
        if d.get('Programa') is not None:
            filas.append(d)
    return cabecera, filas


def normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^\w\s]', ' ', sin_tildes.lower()).split())


def resumen(cabecera, filas, corto, largo):
    print(f'{len(filas)} filas · columnas: {", ".join(cabecera)}')
    if faltan := [c for c in POSIBLES if c not in cabecera]:
        print(f'  sin datos en ninguna fila (no salieron al Excel): {", ".join(faltan)}')

    total = sum(f['Duración'] for f in filas)
    dias = total / 1440
    print(f'\nTotal: {total} minutos = {dias:g} días', end='')
    print('' if total % 1440 == 0 else '   <-- NO da días enteros: el primer o el último bloque está corrido')
    if filas:
        print(f'Desde {filas[0]["Fecha"]:%d/%m} {filas[0]["Hora"]:%H:%M} '
              f'hasta {filas[-1]["Fecha"]:%d/%m} {filas[-1]["Hora"]:%H:%M} (último bloque: {filas[-1]["Duración"]} min)')

    raras = [f for f in filas if f['Duración'] < corto or f['Duración'] > largo]
    print(f'\nDuraciones fuera de {corto}-{largo} minutos: {len(raras)}')
    for f in raras:
        print(f'  N{f["N"]:<4} {f["Día"][:3]} {f["Fecha"]:%d/%m} {f["Hora"]:%H:%M}  {f["Duración"]:>4} min  {f["Programa"]}')

    mayus = [f for f in filas if str(f['Programa']).upper() == str(f['Programa'])
             and re.search(r'[A-ZÁÉÍÓÚÑ]{3}', str(f['Programa']))]
    print(f'\nProgramas en MAYÚSCULAS (salieron tal como vinieron, sin propuesta): {len(mayus)}')
    for f in dict.fromkeys(f['Programa'] for f in mayus):
        print(f'  {f}')

    formas = {}
    for f in filas:
        formas.setdefault(normalizar(f['Programa']), set()).add(str(f['Programa']))
    dobles = {k: v for k, v in formas.items() if len(v) > 1}
    print(f'\nUn mismo programa escrito de dos formas: {len(dobles)}')
    for v in dobles.values():
        print(f'  {" | ".join(sorted(v))}')

    seguidos = [(a, b) for a, b in zip(filas, filas[1:]) if a['Programa'] == b['Programa']]
    print(f'\nEl mismo programa dos veces seguidas: {len(seguidos)}')
    for a, b in seguidos:
        print(f'  N{a["N"]} y N{b["N"]}: {a["Fecha"]:%d/%m} {a["Hora"]:%H:%M} y {b["Hora"]:%H:%M}  {a["Programa"]}')


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('xlsx')
    p.add_argument('--resumen', action='store_true', help='totales y lo que llama la atención, en vez de las filas')
    p.add_argument('--corto', type=int, default=10, help='duración mínima normal, en minutos (10)')
    p.add_argument('--largo', type=int, default=240, help='duración máxima normal, en minutos (240)')
    a = p.parse_args()
    try:
        cabecera, filas = leer(a.xlsx)
    except (zipfile.BadZipFile, KeyError, IndexError, ET.ParseError, StopIteration) as e:
        sys.exit(f'{a.xlsx}: no lo pude leer como Excel ({type(e).__name__}). Pasá un .xlsx de salida/.')
    if not filas:
        sys.exit(f'{a.xlsx}: no encontré filas con Programa. ¿Es un EPG de salida/?')
    if a.resumen:
        resumen(cabecera, filas, a.corto, a.largo)
        return
    print('\t'.join(cabecera))
    for f in filas:
        print('\t'.join('' if f[c] is None else
                        f'{f[c]:%d/%m/%Y}' if c == 'Fecha' else
                        f'{f[c]:%H:%M}' if c == 'Hora' else str(f[c]) for c in cabecera))


if __name__ == '__main__':
    main()
