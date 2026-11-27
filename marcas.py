"""Lo que viene pegado al final de un nombre y se escribe igual en todas las señales: TT, DEST, temporada,
capítulo, año, la etapa de un torneo y el patrocinador. Lo usa procesar.py con cada fila, después del lector: lo que el lector ya sacó le gana."""
import re
import unicodedata

# Marcas reconocidas entre paréntesis o después de un separador. Sin acentos: se comparan normalizadas.
TT = {
    '(r)': ('REP', 'REPRISE', 'REPRISSE', 'REPRIS', 'REPRISS', 'REPETICION', 'REPETICAO', 'REPLAY', 'RERUN', 'REPEAT',
            'ENCORE', 'R'),
    '(v)': ('VIVO', 'EN VIVO', 'AO VIVO', 'LIVE', 'V'),
    '(d)': ('DIFERIDO', 'DIF', 'D'),
    '(g)': ('GRABADO', 'GRAVADO', 'G'),
}
DEST = {'A': ('ESTRENO', 'ESTREIA', 'PREMIERE', 'INEDITO', 'INEDITA', 'NEW')}
# En Brasil "Premiere" es también una marca de canales y programas: ahí no se toma como estreno.
DUDOSAS = {'pt': ('PREMIERE',)}
# Las que se reconocen sueltas al final, sin paréntesis ni separador. "VIVO" suelto no, porque hay programas
# que se llaman así ("Lo mejor de Rodeo en Vivo").
SUELTAS = {'TT': ('REP', 'REPRISE', 'REPRISSE', 'REPRIS', 'REPRISS', 'REPETICION', 'REPETICAO'),
           'DEST': ('ESTRENO', 'PREMIERE')}

PALABRA_CAP = r'(?:EPISODIO|EPISODE|EP|CAPITULO|CAP|PROGRAMA|PROG|PGM|CHAPTER)'
PALABRA_TEMP = r'(?:TEMPORADA|TEMP|SEASON)'
SEPARADOR = r'(?:\s*[|:]\s*|\s+-\s+|\s+)'
# La etapa de un torneo entre paréntesis: "(Final)", "(Semifinal #2)", "(Final - Vuelta)", "(Jornada 17)".
ETAPA = re.compile(r'(?:(?:SEMI)?FINAL(?:ES|S)?|(?:CUARTOS|OCTAVOS|DIECISEISAVOS) DE FINAL)(?:\s*#?\s*\d+)?'
                   r'(?:\s*-\s*(?:IDA|VUELTA))?|JORNADA\s*#?\s*\d+')
# El patrocinador al final no es parte del nombre. Si trae un paréntesis no se toca: podría ser una marca.
PATROCINADOR = re.compile(r'\s+(?:PRESENTED|PRES\.)\s+BY\s+[^()]+$')


def sin_acentos(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().upper()


def _marca(palabra, idioma):
    """(columna, valor) si la palabra es una marca de TT o DEST conocida."""
    p = sin_acentos(palabra).strip(' .')
    if p in DUDOSAS.get(idioma, ()):
        return None
    for valor, formas in TT.items():
        if p in formas:
            return 'TT', valor
    for valor, formas in DEST.items():
        if p in formas:
            return 'DEST', valor
    return None


def _una_del_final(texto, idioma, pelicula):
    """(texto sin lo último, columna, valor) si el final del nombre es una marca, o None."""
    plano = sin_acentos(texto)
    # "(REPRISE)", "[AO VIVO]"
    if m := re.search(r'\s*[(\[]([^()\[\]]+)[)\]]$', plano):
        if hallada := _marca(m.group(1), idioma):
            return texto[:m.start()], *hallada
        if m2 := re.fullmatch(r'\s*(\d{4})\s*', m.group(1)):
            anio = int(m2.group(1))
            if 1900 <= anio <= 2100:
                return texto[:m.start()], 'AÑO', anio
        if m2 := re.fullmatch(r'\s*(\d+)\s*[°ºAª]?\s*' + PALABRA_TEMP + r'\s*', m.group(1)):
            return texto[:m.start()], 'NRO TEMP', int(m2.group(1))
        # "(Episode 1)", "(Episódio 3)", "(Ep. 4)"
        if m2 := re.fullmatch(r'\s*' + PALABRA_CAP + r'\.?\s*(?:N[O°º]\.?\s*)?(\d+)\s*', m.group(1)):
            return texto[:m.start()], 'NRO CAP', int(m2.group(1))
        if ETAPA.fullmatch(m.group(1).strip()):
            etapa = ' '.join(texto[m.start():].strip(' ()[]').replace('#', ' ').split())
            return texto[:m.start()], 'TIT CAP', etapa
    if m := PATROCINADOR.search(plano):
        return texto[:m.start()], None, None
    # "| AO VIVO", " - REP"
    if m := re.search(r'(?:\s*\|\s*|\s+-\s+)([A-Z .]+)$', plano):
        if hallada := _marca(m.group(1), idioma):
            return texto[:m.start()], *hallada
    # "BRASILEIRAO REP", "PERROS ESTRENO"
    for columna, formas in SUELTAS.items():
        if (m := re.search(r'\s+(' + '|'.join(formas) + r')\.?$', plano)) and (hallada := _marca(m.group(1), idioma)):
            return texto[:m.start()], *hallada
    # "PARTE 2" va al capítulo; en una película es parte del título ("Harry Potter... Parte 2"), y después de un
    # separador ya es parte del capítulo ("DOCUMENTAL | LA SELVA PARTE 2"), que lo resuelve el patrón.
    if not pelicula and (m := re.search(SEPARADOR + r'(PARTE|PART|PT\.?)\s*(\d+)$', plano)) \
            and not re.search(r'\||:|\s-\s', plano[:m.start()]):
        palabra = texto[m.start(1):m.end(1)]
        return texto[:m.start()], 'TIT CAP', f'{palabra[:1].upper()}{palabra[1:].lower()} {int(m.group(2))}'
    # "EPISODIO 4", "CAP. 12", "PROGRAMA 32", "PGM 7", con o sin "Nº"
    if m := re.search(SEPARADOR + PALABRA_CAP + r'\.?\s*(?:N[O°º]\.?\s*)?(\d+)$', plano):
        return texto[:m.start()], 'NRO CAP', int(m.group(1))
    # "TEMPORADA 3", "TEMP 6", "3° TEMPORADA", "SEASON 2"
    if m := re.search(SEPARADOR + PALABRA_TEMP + r'\.?\s*(\d+)$', plano):
        return texto[:m.start()], 'NRO TEMP', int(m.group(1))
    if m := re.search(SEPARADOR + r'(\d+)\s*[°ºAª]?\s*' + PALABRA_TEMP + r'$', plano):
        return texto[:m.start()], 'NRO TEMP', int(m.group(1))
    # "T2 E5", "S02E05", "T02 EP 05"
    if m := re.search(SEPARADOR + r'[TS]\s*(\d+)\s*(?:E|EP|CAP)\.?\s*(\d+)$', plano):
        return texto[:m.start()], 'NRO TEMP', (int(m.group(1)), int(m.group(2)))
    return None


def separar_marcas(texto, idioma='es', pelicula=False):
    """(nombre sin las marcas del final, {columna: valor}). Si quitarlas dejara el nombre vacío, no se quita nada.
    El patrocinador se borra sin ir a ninguna columna."""
    encontradas = {}
    t = texto.strip()
    while (hallada := _una_del_final(t, idioma, pelicula)) is not None:
        resto, columna, valor = hallada
        resto = resto.rstrip(' |:-')
        if not resto.strip():
            break
        if columna is None:
            pass
        elif columna == 'NRO TEMP' and isinstance(valor, tuple):
            encontradas.setdefault('NRO TEMP', valor[0])
            encontradas.setdefault('NRO CAP', valor[1])
        else:
            # Se lee de atrás para adelante: si una columna aparece dos veces, vale la de más a la derecha.
            encontradas.setdefault(columna, valor)
        t = resto
    return t, encontradas
