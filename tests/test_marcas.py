"""Las marcas que se sacan del nombre en todas las señales, y las que se dejan a propósito."""
import pytest
from marcas import separar_marcas

CASOS = [
    # TT
    ('BRASILEIRAO REP', 'pt', False, 'BRASILEIRAO', {'TT': '(r)'}),
    ('FUTBOL - REP', 'es', False, 'FUTBOL', {'TT': '(r)'}),
    ('DOCTOR WHO (R)', 'es', False, 'DOCTOR WHO', {'TT': '(r)'}),
    ('FRIENDS (RERUN)', 'en', False, 'FRIENDS', {'TT': '(r)'}),
    ('NOTICIERO (EN VIVO)', 'es', False, 'NOTICIERO', {'TT': '(v)'}),
    ('JOGO | AO VIVO', 'pt', False, 'JOGO', {'TT': '(v)'}),
    # DEST
    ('PERROS ESTRENO', 'es', False, 'PERROS', {'DEST': 'A'}),
    ('MASTERCHEF (ESTRENO)', 'es', False, 'MASTERCHEF', {'DEST': 'A'}),
    ('FUTBOL PREMIERE', 'es', False, 'FUTBOL', {'DEST': 'A'}),
    ('GALA (NEW)', 'en', False, 'GALA', {'DEST': 'A'}),
    # Capítulo, temporada y año
    ('EL CHAVO EPISODIO 4', 'es', False, 'EL CHAVO', {'NRO CAP': 4}),
    ('EM REVISTA: PGM 13', 'pt', False, 'EM REVISTA', {'NRO CAP': 13}),
    ('LA ROSA DE GUADALUPE CAP. 12', 'es', False, 'LA ROSA DE GUADALUPE', {'NRO CAP': 12}),
    ('LOS SIMPSON TEMPORADA 3', 'es', False, 'LOS SIMPSON', {'NRO TEMP': 3}),
    ('EL SEÑOR DE LOS CIELOS (3° TEMPORADA)', 'es', False, 'EL SEÑOR DE LOS CIELOS', {'NRO TEMP': 3}),
    ('DR. HOUSE T2 E5', 'es', False, 'DR. HOUSE', {'NRO TEMP': 2, 'NRO CAP': 5}),
    ('SUPERNATURAL S02E05', 'en', False, 'SUPERNATURAL', {'NRO TEMP': 2, 'NRO CAP': 5}),
    ('TITANIC (1997)', 'es', True, 'TITANIC', {'AÑO': 1997}),
    ('EL CHAVO PARTE 2', 'es', False, 'EL CHAVO', {'TIT CAP': 'Parte 2'}),
    # Varias juntas, de atrás para adelante
    ('LA REINA DEL SUR TEMPORADA 2 CAPITULO 14 (REPRISE)', 'es', False, 'LA REINA DEL SUR',
     {'TT': '(r)', 'NRO CAP': 14, 'NRO TEMP': 2}),
    # Lo que se deja como está
    ('LO MEJOR DE RODEO EN VIVO', 'es', False, 'LO MEJOR DE RODEO EN VIVO', {}),
    ('CHECO: NEVER GIVE UP', 'es', False, 'CHECO: NEVER GIVE UP', {}),
    ('PARECE TERAPIA | RAFA OLIVEIRA', 'pt', False, 'PARECE TERAPIA | RAFA OLIVEIRA', {}),
    ('BN 20', 'es', False, 'BN 20', {}),
    ('CINE 51', 'es', False, 'CINE 51', {}),
    ('PROGRAMA 32', 'es', False, 'PROGRAMA 32', {}),
    ('REP', 'es', False, 'REP', {}),
    ('FUTEBOL PREMIERE', 'pt', False, 'FUTEBOL PREMIERE', {}),
    ('HARRY POTTER PARTE 2', 'es', True, 'HARRY POTTER PARTE 2', {}),
    ('DOCUMENTAL | LA SELVA PARTE 2', 'es', False, 'DOCUMENTAL | LA SELVA PARTE 2', {}),
]


@pytest.mark.parametrize('texto, idioma, pelicula, nombre, marcas', CASOS, ids=[c[0] for c in CASOS])
def test_separar_marcas(texto, idioma, pelicula, nombre, marcas):
    assert separar_marcas(texto, idioma, pelicula) == (nombre, marcas)
