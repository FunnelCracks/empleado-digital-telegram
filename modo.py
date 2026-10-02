"""Para quién es el bot, y el nombre y el contacto de la empresa.

El modo se elige una vez, al crear el bot, con dos botones y una
confirmación. Después ya no se puede cambiar: lo que se sube a un bot de
equipo puede ser interno, y un botón que lo abriera al público lo dejaría a
la vista de cualquiera.

Ni la elección ni las preguntas de /empresa y /contacto guardan en qué paso
va nadie. Los botones llevan escrito lo que hacen, y las respuestas llegan
marcadas por Telegram como respuesta a la pregunta del bot.
"""

import logging

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import acceso
import almacen
import menu
import textos
from comun import registrar_comandos, responder, responder_no_permitido

log = logging.getLogger("empleado.modo")

PREFIJO_MODO = "modo:"
ELEGIR = "modo:elegir:"        # + equipo / clientes: pide confirmación
CONFIRMAR = "modo:confirmar:"  # + equipo / clientes: lo fija
VOLVER = "modo:volver"

MAX_NOMBRE = 80
MAX_CONTACTO = 300


# ---------------------------------------------------------------------------
# Elegir el modo
# ---------------------------------------------------------------------------


def _botones_eleccion() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(textos.BOTON_MODO_EQUIPO, callback_data=f"{ELEGIR}{acceso.MODO_EQUIPO}")],
        [InlineKeyboardButton(textos.BOTON_MODO_CLIENTES, callback_data=f"{ELEGIR}{acceso.MODO_CLIENTES}")],
    ])


async def ensenar_eleccion(update: Update) -> None:
    await update.effective_message.reply_text(
        textos.ELEGIR_MODO, parse_mode="HTML", reply_markup=_botones_eleccion()
    )


async def pulsacion_modo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pulsacion = update.callback_query
    await pulsacion.answer()
    chat_id = pulsacion.message.chat.id

    if not acceso.es_owner(chat_id):
        await pulsacion.edit_message_text(textos.SOLO_OWNER)
        return

    # Un botón de un mensaje viejo puede seguir ahí. Si el modo ya está
    # elegido, no hace nada más que recordarlo.
    actual = acceso.modo()
    if actual is not None:
        await pulsacion.edit_message_text(textos.modo_ya_elegido(actual))
        return

    datos = pulsacion.data or ""
    if datos == VOLVER:
        await pulsacion.edit_message_text(
            textos.ELEGIR_MODO, parse_mode="HTML", reply_markup=_botones_eleccion()
        )
        return

    if datos.startswith(ELEGIR):
        elegido = datos[len(ELEGIR):]
        if elegido not in acceso.MODOS:
            return
        await pulsacion.edit_message_text(
            textos.confirmar_modo(elegido),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    textos.boton_confirmar_modo(elegido),
                    callback_data=f"{CONFIRMAR}{elegido}",
                )],
                [InlineKeyboardButton(textos.BOTON_VOLVER_A_ELEGIR, callback_data=VOLVER)],
            ]),
        )
        return

    if datos.startswith(CONFIRMAR):
        elegido = datos[len(CONFIRMAR):]
        if not await acceso.fijar_modo(elegido):
            # Otra pulsación se ha adelantado. Se cuenta lo que quedó.
            await pulsacion.edit_message_text(textos.modo_ya_elegido(acceso.modo() or elegido))
            return
        await almacen.registrar_evento("modo_elegido", chat_id, elegido)
        log.info("Modo elegido: %s", elegido)
        if elegido == acceso.MODO_CLIENTES:
            await pulsacion.edit_message_text(textos.MODO_ELEGIDO_CLIENTES, parse_mode="HTML")
            await _arrancar_modo_clientes(update, context, chat_id)
        else:
            await pulsacion.edit_message_text(textos.MODO_ELEGIDO_EQUIPO, parse_mode="HTML")
            await _arrancar_modo_equipo(update, context, chat_id)


async def _arrancar_modo_equipo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    """Lo mismo que hacía el alta del jefe antes de que hubiera modos."""
    codigo = await acceso.establecer_codigo_nuevo()
    mensaje = update.effective_message
    await mensaje.reply_text(textos.bienvenida_owner(codigo), parse_mode="HTML")
    await mensaje.reply_text(textos.AVISO_DATOS, parse_mode="HTML")
    await mensaje.reply_text(
        textos.SIGUIENTE_PASO_DOCUMENTOS,
        parse_mode="HTML",
        reply_markup=menu.teclado_owner(),
    )
    await registrar_comandos(context, chat_id, es_owner=True)


async def _arrancar_modo_clientes(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    mensaje = update.effective_message
    await mensaje.reply_text(textos.AVISO_DATOS_CLIENTES, parse_mode="HTML")
    await mensaje.reply_text(
        textos.enlace_para_clientes(enlace_del_bot(context)),
        parse_mode="HTML",
        reply_markup=menu.teclado_owner(para_clientes=True),
    )
    await registrar_comandos(context, chat_id, es_owner=True, para_clientes=True)
    # Sin nombre ni contacto el bot no sabe presentarse ni a dónde mandar a
    # nadie, así que se pregunta ya. Al contestar el nombre, pregunta el
    # contacto, y al contestar el contacto, explica qué subir.
    await preguntar_nombre(update)


def enlace_del_bot(context: ContextTypes.DEFAULT_TYPE) -> str:
    usuario = getattr(context.bot, "username", "") or ""
    return f"https://t.me/{usuario}" if usuario else "el enlace de tu bot"


async def comando_enlace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder_no_permitido(update, textos.SOLO_OWNER)
        return
    await responder(update, textos.enlace_para_clientes(enlace_del_bot(context)))


# ---------------------------------------------------------------------------
# /empresa y /contacto
# ---------------------------------------------------------------------------
#
# El bot pregunta con el recuadro de respuesta ya abierto (ForceReply) y la
# contestación llega marcada como respuesta a esa pregunta. Se reconoce por
# el texto de la pregunta, así que no hay que recordar nada entre mensajes.


async def preguntar_nombre(update: Update) -> None:
    await update.effective_message.reply_text(
        textos.PREGUNTA_NOMBRE_EMPRESA,
        reply_markup=ForceReply(input_field_placeholder=textos.ESCRIBE_EL_NOMBRE),
    )


async def preguntar_contacto(update: Update) -> None:
    await update.effective_message.reply_text(
        textos.PREGUNTA_CONTACTO,
        reply_markup=ForceReply(input_field_placeholder=textos.ESCRIBE_EL_CONTACTO),
    )


async def comando_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder_no_permitido(update, textos.SOLO_OWNER)
        return
    await preguntar_nombre(update)


async def comando_contacto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder_no_permitido(update, textos.SOLO_OWNER)
        return
    await preguntar_contacto(update)


def _pregunta_contestada(update: Update) -> str | None:
    """Si el mensaje contesta a una de las dos preguntas, dice a cuál."""
    original = getattr(update.effective_message, "reply_to_message", None)
    if original is None or not getattr(original.from_user, "is_bot", False):
        return None
    texto = (original.text or "").strip()
    if texto == textos.PREGUNTA_NOMBRE_EMPRESA:
        return "nombre"
    if texto == textos.PREGUNTA_CONTACTO:
        return "contacto"
    return None


async def respuesta_de_empresa_si_toca(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Atiende la respuesta a /empresa o /contacto. Devuelve si lo era.

    Solo cuenta si la manda el jefe. Un cliente contestando a un mensaje del
    bot es una pregunta más.
    """
    if not acceso.es_owner(update.effective_chat.id):
        return False
    pregunta = _pregunta_contestada(update)
    if pregunta is None:
        return False

    texto = (update.effective_message.text or "").strip()
    if not texto:
        await responder(update, textos.RESPUESTA_VACIA_EMPRESA)
        return True

    if pregunta == "nombre":
        if len(texto) > MAX_NOMBRE:
            await responder(update, textos.demasiado_largo(MAX_NOMBRE))
            return True
        await almacen.actualizar_config(nombre_empresa=texto)
        await almacen.registrar_evento("empresa_cambiada", update.effective_chat.id, texto)
        await responder(update, textos.empresa_guardada(texto))
        # Al crear un bot para clientes se encadena con el contacto.
        if acceso.es_modo_clientes() and not almacen.leer_config().get("contacto"):
            await preguntar_contacto(update)
        return True

    if len(texto) > MAX_CONTACTO:
        await responder(update, textos.demasiado_largo(MAX_CONTACTO))
        return True
    primera_vez = not almacen.leer_config().get("contacto")
    await almacen.actualizar_config(contacto=texto)
    await almacen.registrar_evento("contacto_cambiado", update.effective_chat.id)
    await responder(update, textos.contacto_guardado(texto))
    if primera_vez and acceso.es_modo_clientes():
        await responder(update, textos.SIGUIENTE_PASO_CLIENTES)
    return True
