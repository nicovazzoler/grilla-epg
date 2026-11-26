"""Lo que viene pegado al final de un nombre y se escribe igual en todas las señales: TT, DEST, temporada,
capítulo y año. Lo usa procesar.py con cada fila, después del lector: lo que el lector ya sacó le gana."""
import re
import unicodedata

# Marcas reconocidas entre paréntesis o después de un separador. Sin acentos: se comparan normalizadas.
TT = {
    '(r)': ('REP', 'REPRISE', 'REPRISSE', 'REPRIS', 'REPRISS', 'REPETICION', 'REPETICAO', 'REPLAY', 'R'),
    '(v)': ('VIVO', 'EN VIVO', 'AO VIVO', 'LIVE', 'V'),
    '(d)': ('DIFERIDO', 'DIF', 'D'),
    '(g)': ('GRABADO', 'GRAVADO', 'G'),
}
DEST = {'A': ('ESTRENO', 'ESTREIA', 'PREMIERE', 'INEDITO', 'INEDITA')}
# Las únicas que se reconocen sueltas al final, sin paréntesis ni separador: ningún título termina así.
# "VIVO" o "ESTRENO" sueltos no, porque hay programas que se llaman así ("Lo mejor de Rodeo en Vivo").
SUELTAS = ('REP', 'REPRISE', 'REPRISSE', 'REPRIS', 'REPRISS', 'REPETICION', 'REPETICAO')

PALABRA_CAP = r'(?:EPISODIO|EPISODE|EP|CAPITULO|CAP|PROGRAMA|PROG|PGM|CHAPTER)'
PALABRA_TEMP = r'(?:TEMPORADA|TEMP|SEASON)'
SEPARADOR = r'(?:\s*[|:]\s*|\s+-\s+|\s+)'


def sin_acentos(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().upper()


def _marca(palabra):
    """(columna, valor) si la palabra es una marca de TT o DEST conocida."""
    p = sin_acentos(palabra).strip(' .')
    for valor, formas in TT.items():
        if p in formas:
            return 'TT', valor
    for valor, formas in DEST.items():
        if p in formas:
            return 'DEST', valor
    return None


def _una_del_final(texto):
    """(texto sin lo último, columna, valor) si el final del nombre es una marca, o None."""
    plano = sin_acentos(texto)
    # "(REPRISE)", "[AO VIVO]"
    if m := re.search(r'\s*[(\[]([^()\[\]]+)[)\]]$', plano):
        if hallada := _marca(m.group(1)):
            return texto[:m.start()], *hallada
        if m2 := re.fullmatch(r'\s*(\d{4})\s*', m.group(1)):
            anio = int(m2.group(1))
            if 1900 <= anio <= 2100:
                return texto[:m.start()], 'AÑO', anio
        if m2 := re.fullmatch(r'\s*(\d+)\s*[°ºAª]?\s*' + PALABRA_TEMP + r'\s*', m.group(1)):
            return texto[:m.start()], 'NRO TEMP', int(m2.group(1))
    # "| AO VIVO", " - REP"
    if m := re.search(r'(?:\s*\|\s*|\s+-\s+)([A-Z .]+)$', plano):
        if hallada := _marca(m.group(1)):
            return texto[:m.start()], *hallada
    # "BRASILEIRAO REP", "PARECE TERAPIA REPRISE."
    if m := re.search(r'\s+(' + '|'.join(SUELTAS) + r')\.?$', plano):
        return texto[:m.start()], 'TT', '(r)'
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


def separar_marcas(texto):
    """(nombre sin las marcas del final, {columna: valor}). Si quitarlas dejara el nombre vacío, no se quita nada."""
    encontradas = {}
    t = texto.strip()
    while (hallada := _una_del_final(t)) is not None:
        resto, columna, valor = hallada
        resto = resto.rstrip(' |:-')
        if not resto.strip():
            break
        if columna == 'NRO TEMP' and isinstance(valor, tuple):
            encontradas.setdefault('NRO TEMP', valor[0])
            encontradas.setdefault('NRO CAP', valor[1])
        else:
            # Se lee de atrás para adelante: si una columna aparece dos veces, vale la de más a la derecha.
            encontradas.setdefault(columna, valor)
        t = resto
    return t, encontradas
