# Grillas a EPG

Convierte la programación semanal que mandan las señales de TV —en Excel, Word o PDF, cada una con su formato— en un
EPG en Excel con el mismo formato para todas.

Lo estructural (horarios, duraciones, ciclos, temporada, en vivo o repetición) lo resuelve el código, siempre igual.
Los nombres de los programas se corrigen en capas:

1. **Diccionario**: lo ya aprobado se corrige solo.
2. **Parecido de texto**: "MUQLING" se reconoce como "MUQILING" sin llamar a ningún modelo.
3. **Modelo**: lo que no se parece a nada conocido lo propone Claude, siguiendo las reglas de la señal. Si el nombre
   trae algo pegado que va en otra columna, lo separa: "BRASILEIRÃO 2026" → TIT PRINC *Brasileirão*, TIT TEMP *2026*.
4. **Persona**: `aprobar.py` muestra lo nuevo en una línea; Enter acepta y se corrige solo lo que está mal.
   Lo aprobado pasa al diccionario, y hasta entonces esas filas salen con *REVISAR: sí* en el Excel.

Dos nombres que difieren en un número (BN 20 y BN 30) nunca se corrigen solos por parecido: los ve el modelo y los
aprueba una persona.

Cada semana el modelo ve solo lo nuevo, así que su uso baja en vez de crecer. Cada corrida queda en `registro.csv`.

## Columnas

Las del formato del EPG, en su orden (`escribir_epg.py`): TIT ORIG, TIT PRINC, CICLO, NRO TEMP, TIT TEMP, NRO CAP,
TIT CAP, DEST, TT, DIRECTOR, A1–A3, PAIS, AÑO, SIN LARGA, ARG LARGO, DOB, SUB, SAP, CC, LS, GENERO, y los títulos,
sinopsis y argumentos en inglés y portugués, y RATING. Salen solo las que tienen algún dato.

En una señal en portugués o en inglés, su título y su capítulo van en el lugar de TIT PRINC y TIT CAP
(TIT PORT y TIT CAP PORT, por ejemplo), y lo que venga en castellano pasa al final.

Antes de terminar se controla el formato de cada celda: textos de hasta 99 caracteres (2000 las sinopsis y argumentos),
DUR de 1 a 720, AÑO de 4 dígitos, DEST A o M, TT (v), (d), (r) o (g), DOB y SUB con 1, SAP, CC y LS con X.
Lo que no cumple se lista como error de formato. TIT PRINC (o el título del idioma de la señal) no puede quedar vacío
en ninguna fila, y TIT ORIG, TIT ING y TIT PORT tampoco si la señal los trae.

## Semanal

Algunas señales mandan semanas que terminan a mitad de mes y el EPG se completa hasta fin de ese mes repitiendo la
última semana: `python procesar.py <señal> <grillas> --semanal`. No entra ningún programa que empiece en el mes
siguiente, y el último del mes dura lo que dura aunque termine después. En los días repetidos:

- Las películas pasan a su ciclo ("Cine de Oro", "Butaca América") o a "Película" si no tienen, sin ningún otro dato.
- Los torneos y eventos especiales pasan al nombre de la señal, también sin ningún otro dato.
- El resto queda igual, sin NRO CAP ni TIT CAP.

Qué es película y qué es evento lo marca el lector de cada señal y, para los nombres nuevos, lo propone el modelo
como TIPO junto con el resto (película, evento o programa) y queda en el diccionario al aprobarlo.

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

## La web

`web/` es lo mismo con pantalla: subir las grillas, ver qué resolvió cada capa, revisar los nombres nuevos con su
contexto (día, hora, qué va antes y después), bajar el Excel, el historial de corridas y el diccionario para buscar y
corregir. Llama a las mismas funciones de `procesar.py`; lo que cambia es dónde vive el diccionario.

- **La base** (PostgreSQL en Railway, SQLite local) tiene el diccionario, cada corrida con las filas que leyó el lector
  y los pendientes. El archivo de la señal no se guarda: se lee desde una carpeta temporal que se borra al terminar.
  Las corridas se borran a los 30 días.
- **El diccionario** arranca, la primera vez, con los JSON de `diccionario/`. Desde ahí la fuente es la base; el botón
  "exportar .json" lo baja en el mismo formato.
- **El EPG se arma de nuevo cada vez que se pide**, con el diccionario de ese momento: lo que se aprueba entra sin volver
  a subir la grilla.

Local:

```
APP_USUARIO=nico APP_CLAVE=algo uvicorn web.app:app --port 8011
```

En Railway, un servicio desde este repo (arranca con el `Procfile`) más un PostgreSQL, y estas variables:

| Variable | Qué es |
|---|---|
| `DATABASE_URL` | La pone Railway al conectar el PostgreSQL |
| `APP_USUARIO`, `APP_CLAVE` | El único usuario. Sin las dos no entra nadie |
| `SECRET_KEY` | Firma la sesión. Sin ella anda igual, pero cada deploy te desloguea |
| `ANTHROPIC_API_KEY` | Para las propuestas del modelo. Sin ella lo nuevo queda pendiente sin propuesta |

## Revisarlo antes de mandarlo

```
python leer_epg.py salida/<archivo>.xlsx --resumen    # totales, duraciones raras, nombres repetidos
python leer_epg.py salida/<archivo>.xlsx              # las filas en TSV, para grep
```

`leer_epg.py` lee el Excel con la biblioteca estándar: no hace falta openpyxl ni abrir Excel.

El agente `revisor-epg` (en `.claude/agents/`) hace esa revisión completa: cruza el EPG con los
pendientes, el diccionario y las reglas de la señal, y reporta por severidad. No modifica nada.

### Demo con RBTV

```
python reiniciar_demo.py
python procesar.py rbtv grade.xlsx                    # frena: hay una hora mal tipeada
python procesar.py rbtv grade.xlsx --hora 288=20:30   # diccionario, parecido y modelo
python aprobar.py rbtv
python procesar.py rbtv grade.xlsx --hora 288=20:30   # todo por diccionario, modelo en 0
```
