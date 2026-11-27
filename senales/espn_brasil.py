"""ESPN Brasil (ESPN 2 a 5): la "Schedule List" en .xls, una fila por programa con fecha, hora, nombre, LTS, rival y
sinopsis. No trae hora de fin."""
import datetime as dt
import re
import xlrd
from senales import espn_latam

NOMBRE = 'ESPN Brasil'
ARCHIVOS = r'^ESPN\d.*\.xls$'
LTS = {'L': ('TT', '(v)'), 'R': ('TT', '(r)'), 'S': ('TT', '(d)'), 'T': ('DEST', 'A')}
# La grilla no dice cuándo termina el último programa: en el EPG va con 240 minutos.
ULTIMO = dt.timedelta(minutes=240)
# La etapa que cierra el nombre ("Copa Messi: Semifinal", "MLB World Series, Jogo 5") va al capítulo: traducida en
# TIT CAP y como viene en TIT CAP PORT.
FASE = re.compile(r'(?:Final\b.*|Semifina(?:l|is)|Quartas[- ]de[- ]Final|Oitavas[- ]de[- ]Final|'
                  r'(?:Primeira|Segunda|Terceira) Fase|Fase de Grupos|Play-Off de Acesso|Ida|Volta|Jogo \d+)', re.I)
TRADUCCION = {'quartas de final': 'Cuartos de final', 'oitavas de final': 'Octavos de final', 'volta': 'Vuelta'}


def rival(texto):
    """'Neftchi (Uzb) vs. Al Hilal (Ksa)': el país en minúsculas, como va en el EPG."""
    return re.sub(r'\(([A-Z]{3})\)', lambda m: f'({m.group(1).title()})', espn_latam.limpio(texto)) or None


def fase(nombre):
    """(nombre sin la fase, fase en castellano, fase en portugués)."""
    partes = list(re.finditer(r'[^:,]+', nombre))
    corte = len(partes)
    while corte > 1 and FASE.fullmatch(partes[corte - 1].group(0).strip()):
        corte -= 1
    if corte == len(partes):
        return nombre, None, None
    fases = [p.group(0).strip() for p in partes[corte:]]
    es = [TRADUCCION.get(f.lower().replace('-', ' '), f) for f in fases]
    return nombre[:partes[corte].start()].rstrip(' :,'), ' - '.join(es), ' - '.join(fases)


def hora(valor):
    if isinstance(valor, dt.time):
        return dt.timedelta(hours=valor.hour, minutes=valor.minute)
    if isinstance(valor, float):
        return dt.timedelta(seconds=round(valor * 86400) % 86400)
    t = dt.datetime.strptime(espn_latam.limpio(valor), '%H:%M')
    return dt.timedelta(hours=t.hour, minutes=t.minute)


def leer(archivos, horas_corregidas):
    filas, canal = [], None
    for archivo in archivos:
        hoja = xlrd.open_workbook(archivo).sheet_by_name('Schedule List')
        for n in range(1, hoja.nrows):
            red, fecha, h, nombre, lts, contra, *_ = hoja.row_values(n) + [''] * 2
            if not espn_latam.limpio(fecha):
                continue
            canal = canal or espn_latam.limpio(red).upper()
            dia = dt.datetime.strptime(espn_latam.limpio(fecha).split()[-1], '%m/%d/%Y')
            inicio = dia + hora(horas_corregidas.get(n + 1, h))
            nombre = re.sub(r'\s*\(se necessário\)', '', espn_latam.limpio(nombre))
            crudo, fase_es, fase_pt = fase(nombre)
            datos, ciclo = {}, None
            if documental := espn_latam.serie_o_ciclo(nombre):
                crudo, datos['TIT CAP'], ciclo = documental
                datos['CICLO'] = ciclo
            if marca := LTS.get(espn_latam.limpio(lts).upper()):
                datos[marca[0]] = marca[1]
            if ((equipos := rival(contra)) or fase_es) and not documental:
                datos['TIT CAP'] = espn_latam.capitulo(equipos, fase_es)
                datos['TIT CAP PORT'] = espn_latam.capitulo(equipos and equipos.replace(' vs. ', ' x '), fase_pt)
            if m := espn_latam.TEMPORADA.search(crudo):
                datos['TIT TEMP'] = m.group(1)
                crudo = crudo[:m.start()]
            filas.append({'ref': f'fila {n + 1}', 'inicio': inicio, 'crudo': crudo,
                          'tipo': 'pelicula' if ciclo else 'evento' if equipos else None, 'ciclo': ciclo,
                          'datos': datos,
                          'compacto': bool(equipos and ' vs. ' in equipos) and espn_latam.limpio(lts).upper() != 'L'})
    cierre = filas[-1]['inicio'] + ULTIMO
    # Sin hora de fin, la duración es hasta que empieza el siguiente.
    for f, siguiente in zip(filas, [g['inicio'] for g in filas[1:]] + [cierre]):
        f['compacto'] = f['compacto'] and siguiente - f['inicio'] <= espn_latam.DURACION_COMPACTO
    # El EPG a mano tiene la disposición de las señales en castellano, con el portugués al final.
    return {'canal': f'{canal or "ESPN"}_Brasil', 'etiqueta': NOMBRE, 'idioma': 'es', 'filas': filas,
            'cierre': cierre}


def completar(filas):
    espn_latam.poner_compacto(filas, espn_latam.COMPACTO)
    espn_latam.copiar_titulos(filas, (('TIT PORT', 'TIT PRINC'), ('TIT CAP PORT', 'TIT CAP'),
                                      ('TIT ING', 'TIT PRINC'), ('TIT CAP ING', 'TIT CAP')))
