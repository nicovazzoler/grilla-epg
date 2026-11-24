"""Las tres tablas: el diccionario aprobado, cada corrida con sus filas leídas y lo que quedó para revisar."""
import datetime as dt
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def ahora_utc():
    """La hora en UTC, sin zona: así se guarda todo. La pantalla la muestra en la hora del navegador."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def iso_utc(momento):
    """Para la API: con la Z, el navegador sabe que es UTC y la pasa a hora argentina."""
    return momento.isoformat(timespec='minutes') + 'Z'


class Entrada(Base):
    """Un nombre aprobado: cómo vino en la grilla y cómo va repartido en columnas."""
    __tablename__ = 'diccionario'
    __table_args__ = (UniqueConstraint('senal', 'crudo'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    senal: Mapped[str] = mapped_column(String(40), index=True)
    crudo: Mapped[str] = mapped_column(String(300))
    reparto: Mapped[dict] = mapped_column(JSON)
    # De dónde salió: repo (la carga inicial), parecido, modelo o a mano.
    capa: Mapped[str] = mapped_column(String(20))
    aprobada: Mapped[dt.datetime] = mapped_column(DateTime, default=ahora_utc)


class Senal(Base):
    """El nombre que se le puso a una señal desde la pantalla. Sin fila, vale el NOMBRE de su lector."""
    __tablename__ = 'senales'

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))


class Corrida(Base):
    """Una vez que se procesaron grillas. Guarda las filas leídas, no el archivo de la señal."""
    __tablename__ = 'corridas'

    id: Mapped[int] = mapped_column(primary_key=True)
    senal: Mapped[str] = mapped_column(String(40), index=True)
    creada: Mapped[dt.datetime] = mapped_column(DateTime, default=ahora_utc, index=True)
    archivos: Mapped[list] = mapped_column(JSON)
    semanal: Mapped[bool] = mapped_column(Boolean, default=False)
    # canal, etiqueta, idioma, cierre y filas, como los devuelve el lector.
    leido: Mapped[dict] = mapped_column(JSON)
    capas: Mapped[dict] = mapped_column(JSON)
    problema_modelo: Mapped[str | None] = mapped_column(Text)
    minutos_a_mano: Mapped[int] = mapped_column(Integer)

    pendientes: Mapped[list['Pendiente']] = relationship(back_populates='corrida', cascade='all, delete-orphan',
                                                         order_by='Pendiente.id')


class Pendiente(Base):
    """Un nombre nuevo de una corrida, con la propuesta y dónde aparece en la grilla."""
    __tablename__ = 'pendientes'

    id: Mapped[int] = mapped_column(primary_key=True)
    corrida_id: Mapped[int] = mapped_column(ForeignKey('corridas.id', ondelete='CASCADE'), index=True)
    crudo: Mapped[str] = mapped_column(String(300))
    propuesta: Mapped[dict] = mapped_column(JSON)
    capa: Mapped[str] = mapped_column(String(20))
    nota: Mapped[str] = mapped_column(Text, default='')
    contexto: Mapped[dict] = mapped_column(JSON)
    # pendiente, aprobado o salteado
    estado: Mapped[str] = mapped_column(String(12), default='pendiente')

    corrida: Mapped[Corrida] = relationship(back_populates='pendientes')
