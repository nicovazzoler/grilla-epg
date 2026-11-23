# Grilla a EPG, con IA solo donde hace falta

Convierte la grade semanal de RBTV en un EPG en Excel. Lo estructural (horarios, duraciones,
ciclos, año, en vivo o repetición) lo resuelve el código, siempre igual. Los nombres se corrigen en capas:

1. **Diccionario**: lo ya aprobado se corrige solo.
2. **Parecido de texto**: "MUQLING" se reconoce como "MUQILING" sin llamar a ningún modelo.
3. **Modelo**: lo que no se parece a nada conocido se lo propone Claude, siguiendo `reglas/rbtv.md`.
4. **Persona**: `aprobar.py` muestra lo nuevo, y lo aprobado pasa al diccionario.

Cada semana el modelo ve solo lo nuevo, así que su uso baja en vez de crecer.

## Correrlo

```
pip install -r requirements.txt
copy .env.example .env        # y poné tu ANTHROPIC_API_KEY (sin clave anda igual: lo nuevo queda pendiente)

python reiniciar_demo.py
python procesar.py grade_rbtv_23-29_nov.xlsx                    # frena: hay una hora mal tipeada
python procesar.py grade_rbtv_23-29_nov.xlsx --hora 288=20:30   # diccionario, parecido y modelo
python aprobar.py
python procesar.py grade_rbtv_23-29_nov.xlsx --hora 288=20:30   # todo por diccionario, modelo en 0
```

El Excel queda en `salida/`.
