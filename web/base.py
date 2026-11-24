"""La base: PostgreSQL en Railway (DATABASE_URL), SQLite local si no hay ninguna."""
import datetime as dt
import json
import os
import re
from pathlib import Path
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from web.modelos import Base, Entrada, Corrida, ahora_utc

RAIZ = Path(__file__).resolve().parent.parent
DIAS_QUE_SE_GUARDA_UNA_CORRIDA = 30


def url_de_la_base():
    url = os.environ.get('DATABASE_URL', f'sqlite:///{RAIZ / "grilla_epg.db"}')
    # El driver va explícito: sin él, cada versión de SQLAlchemy elige otro (psycopg2 o psycopg 3).
    # Railway la da como postgres://, que SQLAlchemy ya no acepta.
    return re.sub(r'^postgres(ql)?://', 'postgresql+psycopg://', url)


motor = create_engine(url_de_la_base(), pool_pre_ping=True)
Sesion = sessionmaker(motor, expire_on_commit=False)


def sesion_db():
    with Sesion() as db:
        yield db


def sembrar_diccionarios(db, senales):
    """La primera vez, cada señal arranca con el diccionario del repo. Después la base es la única fuente."""
    for senal in senales:
        if db.scalar(select(func.count()).select_from(Entrada).where(Entrada.senal == senal)):
            continue
        archivo = RAIZ / 'diccionario' / f'{senal}.json'
        if not archivo.exists():
            continue
        for crudo, valor in json.loads(archivo.read_text(encoding='utf-8')).items():
            reparto = {'TIT PRINC': valor} if isinstance(valor, str) else valor
            db.add(Entrada(senal=senal, crudo=crudo, reparto=reparto, capa='repo'))
    db.commit()


def borrar_corridas_viejas(db):
    limite = ahora_utc() - dt.timedelta(days=DIAS_QUE_SE_GUARDA_UNA_CORRIDA)
    for corrida in db.scalars(select(Corrida).where(Corrida.creada < limite)):
        db.delete(corrida)
    db.commit()


def preparar(senales):
    Base.metadata.create_all(motor)
    with Sesion() as db:
        sembrar_diccionarios(db, senales)
        borrar_corridas_viejas(db)
