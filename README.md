# Grillas a EPG

Convierte la programación semanal que mandan las señales de TV —en Excel, Word o PDF, cada una con su formato— en un
EPG en Excel con el mismo formato para todas.

Lo estructural (horarios, duraciones, ciclos, temporada, en vivo o repetición) lo resuelve el código, siempre igual.
Los nombres de los programas se corrigen en capas:

1. **Diccionario**: lo ya aprobado se corrige solo.
2. **Parecido de texto**: "MUQLING" se reconoce como "MUQILING" sin llamar a ningún modelo.
3. **Modelo**: lo que no se parece a nada conocido lo propone Claude, siguiendo las reglas de la señal. Si el nombre
   trae algo pegado que va en otra columna, lo separa: "BRASILEIRÃO 2026" → Programa *Brasileirão*, Tít. Temp. *2026*.
4. **Persona**: `aprobar.py` muestra lo nuevo en una línea; Enter acepta y se corrige solo lo que está mal.
   Lo aprobado pasa al diccionario, y hasta entonces esas filas salen con *Revisar: sí* en el Excel.

Dos nombres que difieren en un número (BN 20 y BN 30) nunca cuentan como parecidos: casi siempre son programas distintos.

Cada semana el modelo ve solo lo nuevo, así que su uso baja en vez de crecer. Cada corrida queda en `registro.csv`.

## Señales

| Señal | Formato | Lo difícil |
|---|---|---|
| `rbtv` | Excel en lista | Nombres escritos distinto según el día |
| `america` | Excel en cuadrícula | El programa empieza en el borde del recuadro, no donde está el nombre |
| `monterrey` | PDF | Los recuadros se arman con las líneas del PDF; conductores a A1–A3 |
| `canal51` | Word | Títulos de películas mal escritos; estreno solo la primera vez en la semana |

Agregar una señal es sumar su lector en `senales/`, sus reglas en `reglas/` y su diccionario en `diccionario/`.

## Correrlo

```
pip install -r requirements.txt
copy .env.example .env        # y poné tu ANTHROPIC_API_KEY (sin clave anda igual: lo nuevo queda pendiente)

python procesar.py <señal> <grilla> [<grilla> ...]    # varias semanas van a un solo EPG
python aprobar.py <señal>
```

El Excel queda en `salida/`. Las grillas no se suben al repo.

### Demo con RBTV

```
python reiniciar_demo.py
python procesar.py rbtv grade.xlsx                    # frena: hay una hora mal tipeada
python procesar.py rbtv grade.xlsx --hora 288=20:30   # diccionario, parecido y modelo
python aprobar.py rbtv
python procesar.py rbtv grade.xlsx --hora 288=20:30   # todo por diccionario, modelo en 0
```
