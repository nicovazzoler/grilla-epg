"""Deja el diccionario como estaba la semana anterior, para correr la demo desde el principio."""
import shutil
from procesar import DICCIONARIO, PENDIENTES

shutil.copy(DICCIONARIO.with_name('rbtv_semana_anterior.json'), DICCIONARIO)
PENDIENTES.unlink(missing_ok=True)
print('Diccionario de la semana anterior restaurado.')
