# Próximos

Lo que quedó pensado y todavía no se hizo, de lo más grande a lo más chico.

## Un agente que arma lectores

Se le pasa una carpeta por señal y escribe el lector hasta que `probar.py` dé igual:

```
<señal>/
  ejemplo/   grilla + esperado.xlsx      ← lo ve el agente
  prueba/    grilla + esperado.xlsx      ← lo corre una persona al final
```

- La semana de `prueba/` el agente no la ve nunca: si el lector anda con una grilla que no vio, entendió el formato;
  si solo anda con la que vio, se la aprendió.
- Que sea de otro mes que la de `ejemplo/`: el cambio de mes, los feriados y los cambios de formato son lo que rompe.
- Al terminar, buscar en el lector nombres de programas u horarios de la grilla escritos a mano.

## Familias de señales

- **Un lector genérico para "Excel en lista"** (Claro Sports, RBTV y las que vengan así), con una ficha por señal:
  qué columna es la hora, el formato de la fecha, qué palabra marca el vivo. Una señal nueva de ese tipo es llenar la
  ficha, no escribir código.
- **Televisa:** las locales vienen con el mismo PDF y casi los mismos programas. Un lector para todas.
- **Diccionario en dos niveles:** el de la familia y el de la señal, que le gana. Lo que se aprueba va por defecto a
  la familia (en el pack de ESPN, aprobar una vez sirve para las 20). El idioma no los separa: el título queda como
  viene y la columna la decide el idioma de cada señal.

## Lectores que no se rompan con poco

- Buscar las columnas por su título ("HORA", "PROGRAMA") y no por posición.
- Si falta algo que esperaba, frenar diciendo qué falta, nunca seguir y armar mal.

## Catálogo de marcas compartido

- Una sola lista para todas las señales con las formas de marcar TT y DEST, en castellano, portugués e inglés: vivo,
  en vivo, ao vivo, live; reprise, reprisse, rep, repetición, replay; diferido; grabado; estreno, estreia, premiere,
  inédito.
- Lo que sobra al final de un nombre con pinta de marca (entre paréntesis, después de `|` o `-`, una palabra corta)
  sale en correcciones como "¿esto es una marca?" en vez de quedar en el título.
- Lo que se confirma se suma al catálogo, como el diccionario. Caso que lo motivó: "BRASILEIRAO REP" hoy sale sin (r)
  y, una vez aprobado el nombre, sigue saliendo sin (r) todas las semanas sin que nada avise.

## El modelo

- **Candidatos en vez de los primeros 40.** Hoy le van como ejemplo las primeras 40 entradas del diccionario. Con un
  diccionario grande, el nombre que coincide puede no estar entre ellas. Mandarle las más parecidas a cada nombre nuevo.
- **Contexto para decidir si es película:** duración, cuántas veces pasa en la semana, año y ciclo. Hoy ve solo el
  nombre y, con razón, pregunta. Lo que es una excepción (un documental largo) va en las reglas de la señal.
- **Que pueda proponer TT y DEST** cuando el nombre trae una marca que el lector no conoce.
- **Bug:** si el modelo dice TIPO "programa" para algo que el lector marcó película (por el año o el ciclo), gana el
  modelo y la marca se pierde. Tiene que ganar el lector, como en el resto de las columnas.

## Chicos

- `leer_epg.py` y `.claude/agents/revisor-epg.md` todavía nombran columnas viejas ("Programa").
