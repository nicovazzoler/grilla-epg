# Grillas a EPG

Convierte la programación semanal que mandan las señales de TV —en Excel, Word o PDF, cada una con su formato— en un
EPG en Excel con el mismo formato para todas.

Lo estructural (horarios, duraciones, ciclos, temporada, en vivo o repetición) lo resuelve el código, siempre igual.
Los nombres de los programas se corrigen en capas:

1. **Diccionario**: lo ya aprobado se corrige solo.
2. **Patrón**: un programa que trae una parte que cambia cada semana después de un separador
   ("PARECE TERAPIA | RAFA OLIVEIRA") se aprueba una vez como patrón y desde ahí se resuelve solo: el programa va a
   TIT PRINC y lo que sigue a TIT CAP, escrito como en el ejemplo aprobado. Si esa parte es una frase con nombres
   propios adentro, la escribe el modelo y queda para revisar. Sin separador no es patrón: "COPA LIBERTADORES
   HIGHLIGHTS" es otro programa.
3. **Parecido de texto**: "MUQLING" se reconoce como "MUQILING" sin llamar a ningún modelo.
4. **Modelo**: lo que no se parece a nada conocido lo propone Claude, siguiendo las reglas de la señal. Si el nombre
   trae algo pegado que va en otra columna, lo separa: "BRASILEIRÃO 2026" → TIT PRINC *Brasileirão*, TIT TEMP *2026*.
5. **Persona**: `aprobar.py` muestra lo nuevo en una línea; Enter acepta, "p" lo acepta como patrón y se corrige solo
   lo que está mal.
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
| `clarosports` | Excel en lista | El torneo y el partido vienen pegados; la fecha, mes/día leída al revés |
| `espn_latam` | Excel en lista (Programming Grid) | Las 16 LATAM y Premium: torneo, deporte y partido en un renglón; huecos y superpuestos |
| `espn_ing` | Excel en lista (Programming Grid) | 1A, 4A, 76A y 99A: el mismo lector que LATAM, en inglés y con su diccionario |
| `espn_brasil` | Excel en lista (Schedule List) | ESPN 2 a 5: la fase del torneo va al capítulo, traducida; sin hora de fin |

Agregar una señal es sumar su lector en `senales/`, sus reglas en `reglas/` y su diccionario en `diccionario/`.

## Correrlo

```
pip install -r requirements.txt
copy .env.example .env        # y poné tu ANTHROPIC_API_KEY (sin clave anda igual: lo nuevo queda pendiente)

python procesar.py <señal> <grilla> [<grilla> ...]    # varias semanas van a un solo EPG
python aprobar.py <señal>
```

El Excel queda en `salida/`. Las grillas no se suben al repo.

## Antes de un PR: probar.py

`python probar.py` corre cada grilla de `referencias/<señal>/<caso>/` y compara el EPG contra su `esperado.xlsx`,
celda por celda. Los nombres los toma del esperado, así que lo que prueba es el lector y el armado, no el diccionario:
si un cambio mueve algo sin querer, dice en qué fila y columna. Un caso nuevo es una carpeta con las grillas, el EPG
bueno como `esperado.xlsx` y, si hace falta, `opciones.json` (`{"semanal": true, "horas": {"288": "20:30"}}`). Si
el esperado cubre solo el final de la grilla, `"desde": "2026-11-21 00:00"` deja afuera lo de antes.

`referencias/` no se sube: son grillas del laburo.

`python -m pytest tests` prueba `marcas.py`, lo que se saca del final de un nombre en todas las señales: repetición, vivo, estreno, capítulo, temporada, año, "Parte 2", la etapa de un torneo ("(Semifinal #2)") y el patrocinador ("Presented by …"). Una forma nueva se suma ahí con su caso en `tests/test_marcas.py`, y también los nombres que se tienen que quedar como están.

## La web

`web/` es lo mismo con pantalla: subir las grillas, ver qué resolvió cada capa, revisar los nombres nuevos con su
contexto (día, hora, qué va antes y después) y aceptarlos de a uno o todos juntos, bajar el Excel, las corridas con
lo que trabajó el modelo en cada una, y el diccionario agrupado por programa para buscar, cambiar un título en todos sus
nombres de una vez, sacar una entrada y cambiar el nombre de la señal (el que llevan los eventos de un semanal).
Llama a las mismas funciones de `procesar.py`; lo que cambia es dónde vive el diccionario.

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

Cómo lee cada señal, en castellano y sin código: `docs/LECTORES.md`. Lo pensado para después: `PROXIMOS.md`.

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
