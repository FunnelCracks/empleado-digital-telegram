"""Utilidades que usan varios módulos. Para no repetirlas ni crear ciclos."""

import asyncio
import contextlib
import logging

from telegram import Update
from telegram.constants import ChatAction, ParseMode

import ajustes
import almacen

log = logging.getLogger("empleado.comun")

# Telegram caduca la señal de "escribiendo" a los 5 segundos, así que hay
# que refrescarla antes. Sin esto la gente cree que el bot se ha colgado.
SEGUNDOS_REFRESCO_TYPING = 4


async def responder(update: Update, texto: str) -> None:
    """Envía un mensaje en HTML. Centralizado para no repetir el parse_mode."""
    if update.effective_message:
        await update.effective_message.reply_text(texto, parse_mode=ParseMode.HTML)


def trocear(texto: str, limite: int = ajustes.MAX_CARACTERES_TELEGRAM) -> list[str]:
    """Parte un texto largo en mensajes que quepan en Telegram.

    Corta por párrafos. Si un párrafo no cabe, por líneas. Si una línea no
    cabe, por espacios. Nunca parte una palabra por la mitad salvo que la
    palabra sola ya sea más larga que el límite, que no pasa nunca con texto
    real pero hay que contemplarlo.
    """
    texto = texto.strip()
    if len(texto) <= limite:
        return [texto] if texto else []

    trozos: list[str] = []
    actual = ""

    def cerrar() -> None:
        nonlocal actual
        if actual.strip():
            trozos.append(actual.strip())
        actual = ""

    for parrafo in texto.split("\n\n"):
        candidato = f"{actual}\n\n{parrafo}" if actual else parrafo
        if len(candidato) <= limite:
            actual = candidato
            continue
        cerrar()
        if len(parrafo) <= limite:
            actual = parrafo
            continue
        # El párrafo solo ya no cabe: se baja a líneas y luego a palabras.
        for pieza in _partir_fino(parrafo, limite):
            if len(pieza) > limite:
                trozos.append(pieza)
            else:
                candidato = f"{actual}\n{pieza}" if actual else pieza
                if len(candidato) <= limite:
                    actual = candidato
                else:
                    cerrar()
                    actual = pieza
    cerrar()
    return trozos


def _partir_fino(parrafo: str, limite: int) -> list[str]:
    """Baja de párrafo a líneas, y de línea a palabras, hasta que quepa."""
    piezas: list[str] = []
    for linea in parrafo.split("\n"):
        if len(linea) <= limite:
            piezas.append(linea)
            continue
        actual = ""
        for palabra in linea.split(" "):
            candidato = f"{actual} {palabra}" if actual else palabra
            if len(candidato) <= limite:
                actual = candidato
            else:
                if actual:
                    piezas.append(actual)
                # Una palabra sola más larga que el límite: se corta a lo bruto.
                while len(palabra) > limite:
                    piezas.append(palabra[:limite])
                    palabra = palabra[limite:]
                actual = palabra
        if actual:
            piezas.append(actual)
    return piezas


async def responder_largo(update: Update, texto: str) -> None:
    """Manda la respuesta de Claude, troceada si hace falta.

    Sin `parse_mode`: la respuesta viene de un modelo y puede traer
    caracteres que Telegram interpretaría como etiquetas y le harían
    rechazar el mensaje entero. Por eso el system le pide texto plano.
    """
    if not update.effective_message:
        return
    for trozo in trocear(texto) or ["(sin respuesta)"]:
        await update.effective_message.reply_text(trozo)


def hora_local(marca_iso: str) -> str:
    """Pasa una marca UTC del log a hora de España, legible.

    Si el sistema no trae la base de zonas horarias, se queda en UTC antes
    que reventar: una hora mal puesta es un incordio, un bot caído no.
    """
    from datetime import datetime

    try:
        momento = datetime.fromisoformat(marca_iso)
    except ValueError:
        return marca_iso
    try:
        from zoneinfo import ZoneInfo

        momento = momento.astimezone(ZoneInfo("Europe/Madrid"))
    except Exception:
        pass
    return momento.strftime("%d/%m a las %H:%M")


def formatear_evento(linea: str) -> str:
    """Convierte una línea cruda del access.log en algo que se pueda leer."""
    import textos

    partes = linea.split("\t")
    marca = partes[0] if partes else ""
    evento = partes[1] if len(partes) > 1 else ""
    detalle = partes[3].strip() if len(partes) > 3 else ""

    descripcion = textos.EVENTOS.get(evento, evento.replace("_", " "))
    quien = detalle or "alguien"
    return f"  • {hora_local(marca)}: {quien} {descripcion}"


def documentos_cargados() -> list[str]:
    """Nombres de los documentos, siempre ordenados.

    El orden importa más de lo que parece: el bloque cacheado del system se
    construye con esta misma lista y un orden distinto entre peticiones
    invalidaría la caché entera sin dar ningún error.
    """
    return almacen.listar_documentos()


@contextlib.asynccontextmanager
async def escribiendo(update: Update, accion: str = ChatAction.TYPING):
    """Mantiene la señal de actividad mientras dura la operación.

    Se usa como `async with escribiendo(update):`. La tarea se cancela sola
    al salir del bloque, pase lo que pase dentro.
    """
    chat = update.effective_chat

    async def bucle() -> None:
        while True:
            try:
                await chat.send_action(accion)
            except Exception:
                return  # si falla la señal, no es motivo para romper nada
            await asyncio.sleep(SEGUNDOS_REFRESCO_TYPING)

    tarea = asyncio.create_task(bucle()) if chat else None
    try:
        yield
    finally:
        if tarea:
            tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tarea
