"""Deja el diccionario de RBTV como estaba la semana anterior, para correr la demo desde el principio."""
import shutil
from procesar import diccionario_de, pendientes_de

shutil.copy(diccionario_de('rbtv').with_name('rbtv_semana_anterior.json'), diccionario_de('rbtv'))
pendientes_de('rbtv').unlink(missing_ok=True)
print('Diccionario de RBTV de la semana anterior restaurado.')
