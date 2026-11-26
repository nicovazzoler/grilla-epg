# Cómo lee cada señal

Cada señal manda su grilla a su manera. El lector es la parte que entiende ese formato y lo convierte en una lista
de programas con fecha, hora y nombre. De ahí para abajo todo es igual para todas las señales: los nombres pasan por
el diccionario, se calculan las duraciones y se arma el Excel.

Antes de devolver la lista, se revisa que los horarios vayan en orden. Si uno viene antes que el anterior, se frena
y muestra esa fila con las dos de antes y las dos de después, para que se vea cuál está mal tipeada.

Cada lector termina con **qué lo puede romper**: lo que tendría que cambiar en la grilla para que deje de entenderla.

---

## RBTV (Rede Brasil) — Excel en lista

**Cómo viene:** una hoja con los días uno abajo del otro. Arriba de cada día hay una fila con la fecha (en algunas
semanas dice "SEGUNDA", "TERÇA"… en vez de la fecha) y debajo, una fila por programa con la hora en la columna B y
el nombre en la D.

**Qué hace:**
- Recorre las filas de arriba para abajo. Si la fila trae una fecha, cambia de día. Si trae el día escrito en
  portugués, saca la fecha del título de la hoja ("DE 09 A 15 DE NOVEMBRO DE 2026").
- El día de la grade va de 06:00 a 06:00: lo que empieza antes de las 6 se anota con la fecha del día siguiente.
- Del nombre saca las marcas: "AO VIVO" es vivo (v) y "(REPRISE)" es repetición (r). Borra "(AD)" y "(A2)".
- "| TEMP 6 |" pasa a la temporada; un año entre paréntesis al final, "(2019)", pasa al año.
- "CICLO: PELÍCULA" separa el ciclo del nombre. Es película si trae año o si el ciclo dice CINE.
- Es una señal en portugués: los títulos van en TIT PORT y TIT CAP PORT.

**Qué lo puede romper:** que muevan las columnas (busca la hora en B y el nombre en D), que escriban la repetición
distinto ("REP", "REPRISSE": hoy solo reconoce "(REPRISE)") o que cambien el título de la hoja.

---

## América TV (Perú) — Excel en cuadrícula

**Cómo viene:** un .xls con una columna por día y un recuadro con bordes por cada programa. El nombre puede estar
escrito en cualquier renglón del recuadro, no necesariamente arriba.

**Qué hace:**
- Saca el lunes del título ("DEL 23 AL 29 DE NOVIEMBRE DEL 2026").
- Para cada día, busca dónde empiezan los recuadros mirando las **líneas de borde**: el programa empieza en el borde
  de arriba, aunque el nombre esté más abajo. La hora es la de esa fila.
- Junta todo el texto que quedó adentro del recuadro y saca lo que no es nombre: "*SERIE*", "*DOCUMENTAL*" y los
  actores sueltos que ponen dentro de las películas.
- "*MATINEE DE AMERICA*" y "*BUTACA AMERICA*" son ciclos de películas. "FUTBOL EN AMERICA" y "CAMPEONATO DE LUCHA"
  son eventos.
- "(REPETICION)" al final es (r); "(3° TEMPORADA)" pasa a la temporada; a las telenovelas les saca el "TN." de adelante.
- El día de la grilla arranca a las 05:16.

**Qué lo puede romper:** que cambien la cantidad de columnas por día (las tiene fijas), que dibujen los recuadros sin
borde o que cambien el rango de filas de la grilla. Los actores que no están en su lista se cuelan en el nombre.

---

## Televisa Monterrey (C-4.1, C-8.1) — PDF

**Cómo viene:** un PDF por semana con una columna por día y un recuadro por programa. El canal y las fechas vienen
en el nombre del archivo (…C-4.1_MONTERREY-20261116-20261122.pdf).

**Qué hace:**
- El PDF no tiene tabla: tiene líneas negras dibujadas y letras sueltas. El lector arma los recuadros con esas líneas
  y junta las letras que caen adentro de cada uno, renglón por renglón.
- La hora sale de la **altura** del recuadro en la página: arriba son las 00:00, abajo las 24:00, en pasos de 15
  minutos. Si adentro dice "18:30 a 19:00 hrs." manda eso.
- Dentro del recuadro, cada renglón se clasifica: lo que está en mayúsculas es el programa; lo que sigue en minúsculas
  es el título del capítulo; "Con …" son los conductores (van a A1–A3); "VIVO", "GRABADO" y "REPETICIÓN" van a TT;
  "Cap. 12" al capítulo; una duración tipo "1:45" quiere decir que es película.
- "CINE DE ORO", "PELICULA MEXICANA" y "CICLO DE: …" son ciclos de películas. "LIGA MX" es evento.
- El recuadro de las 23:45 que sigue a las 00:00 del día siguiente se junta en uno solo.

**Qué lo puede romper:** que cambien el tamaño o los márgenes de la página (las posiciones de las columnas y de las
00:00 y 24:00 están medidas a mano), que dejen de dibujar las líneas o que cambien el nombre del archivo.

---

## Canal 51 — Word

**Cómo viene:** un .docx por semana. Un renglón con el día ("Lunes 16 de noviembre") y debajo, un renglón por
programa: "06:30AM: Nombre del programa".

**Qué hace:**
- Lee el documento renglón por renglón. Si es un día, cambia de día; si empieza con una hora, es un programa.
- El año no viene: toma el de hoy (y el siguiente si la fecha quedaría a más de medio año, por el cambio de año).
- El día va de 06:00 a 06:00: la madrugada es del día siguiente.
- "Cine 51", "Cine 51-2" o "Cine clásico" adelante quiere decir película, con ese ciclo. El título es lo que sigue a
  los dos puntos, y un año al final pasa al año.
- "Repriss" es repetición (r), salvo en películas, que no llevan TT.
- Estreno (DEST A) solo la primera vez que pasa cada película en la semana, y nunca en una repetición.

**Qué lo puede romper:** que cambien el formato de la hora ("6:30 am", "18:30") o el de la línea del día.

---

## Claro Sports — Excel en lista

**Cómo viene:** una fila por programa con fecha, hora de inicio, hora de fin, duración, nombre, aire (VIVO o
DIFERIDO), rating y sinopsis. El feed (Sudamérica, México) viene en el nombre del archivo.

**Qué hace:**
- La fecha viene escrita mes/día y Excel a veces la lee al revés (el 1/12 queda 12 de enero). De las dos lecturas
  posibles, toma la que sigue a la fecha de la fila anterior.
- VIVO es (v) y DIFERIDO es (d). El rating pasa tal cual y la sinopsis va a ARG LARGO.
- Los "FILLER" se borran: el programa anterior sigue hasta que empieza el siguiente.
- El torneo y el partido vienen pegados y sin separador ("SUPER LIGA DE GRECIA ARIS VS OLYMPIACOS"). El lector tiene
  una lista de torneos conocidos: si el nombre empieza con uno, el torneo va al diccionario y el partido a TIT CAP.

**Qué lo puede romper:** un torneo nuevo que no está en la lista sale entero como título hasta que se suma, y que
muevan las columnas (las lee por posición).

---

## Lo que tienen en común

Casi todo lo que los rompe es lo mismo: **leen por posición** (la columna C, la altura en la página) y **reconocen
marcas escritas de una sola forma**. Las mejoras para eso están en `PROXIMOS.md`.
