"""Tu Empleado Digital: arranque del bot y registro de handlers.

Aqui solo viven el arranque, los handlers de entrada y el reparto. La logica
de cada cosa esta en su modulo.
"""

import logging
import sys

from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import acceso
import ajustes
import almacen
import comandos
import limites
import menu
import textos
from comun import documentos_cargados, responder

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx registra cada peticion a Telegram y ensucia el log sin aportar nada.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("empleado")


def cuantos_documentos() -> int:
    return len(documentos_cargados())


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    nombre = update.effective_user.full_name if update.effective_user else ""

    # Caso 1: ya es el administrador.
    if acceso.es_owner(chat_id):
        await update.effective_message.reply_text(
            textos.owner_vuelve(cuantos_documentos()),
            parse_mode="HTML",
            reply_markup=menu.teclado_owner(),
        )
        await registrar_comandos(context, chat_id, es_owner=True)
        return

    # Caso 2: no hay administrador todavia y el registro automatico esta
    # activo, asi que el primero que escribe se queda con el bot.
    if not acceso.hay_owner() and acceso.registro_automatico_activo():
        await acceso.registrar_owner(chat_id, nombre)
        codigo = await acceso.establecer_codigo_nuevo()
        log.info("Alta de owner: %s (%s)", chat_id, nombre)
        await responder(update, textos.bienvenida_owner(codigo))
        await responder(update, textos.AVISO_DATOS)
        await update.effective_message.reply_text(
            textos.SIGUIENTE_PASO_DOCUMENTOS,
            parse_mode="HTML",
            reply_markup=menu.teclado_owner(),
        )
        await registrar_comandos(context, chat_id, es_owner=True)
        return

    # Caso 3: hay administrador pero no ha dejado codigo puesto. Puede pasar
    # si se fijo OWNER_CHAT_ID por variable y el owner aun no ha hecho /start.
    if not almacen.leer_config().get("codigo_hash"):
        await responder(update, textos.BOT_SIN_PREPARAR)
        return

    # Caso 4: empleado ya autorizado.
    if acceso.esta_autorizado(chat_id):
        await _dar_la_bienvenida(update, context, chat_id)
        return

    # Caso 5: alguien nuevo. Le pedimos el codigo.
    await responder(update, textos.PEDIR_CODIGO)


async def _dar_la_bienvenida(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    """Bienvenida de empleado, con sus botones y su menu de comandos."""
    config = almacen.leer_config()
    await update.effective_message.reply_text(
        textos.codigo_correcto(
            config.get("nombre_empresa", ""),
            config.get("mensaje_bienvenida", ""),
        ),
        parse_mode="HTML",
        reply_markup=menu.teclado_empleado(),
    )
    await registrar_comandos(context, chat_id, es_owner=False)


async def registrar_comandos(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, es_owner: bool
) -> None:
    """Rellena el menu de comandos de la barra de Telegram para ese chat.

    Es distinto para el owner y para los empleados, asi que se pone por chat
    en vez de globalmente. Si falla no pasa nada: los botones siguen ahi.
    """
    lista = menu.COMANDOS_OWNER if es_owner else menu.COMANDOS_EMPLEADO
    try:
        await context.bot.set_my_commands(
            [BotCommand(nombre, descripcion) for nombre, descripcion in lista],
            scope=BotCommandScopeChat(chat_id),
        )
    except Exception:
        log.warning("No he podido registrar los comandos de %s", chat_id)


# ---------------------------------------------------------------------------
# /codigo
# ---------------------------------------------------------------------------


async def comando_codigo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not acceso.es_owner(chat_id):
        await responder(update, textos.SOLO_OWNER)
        return
    codigo = await acceso.establecer_codigo_nuevo()
    await almacen.registrar_evento("codigo_regenerado", chat_id)
    await responder(update, textos.codigo_regenerado(codigo))


# ---------------------------------------------------------------------------
# /ayuda
# ---------------------------------------------------------------------------


async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    nombres = documentos_cargados()

    if acceso.es_owner(chat_id):
        await responder(update, textos.ayuda_owner(len(nombres), nombres))
        return
    if acceso.esta_autorizado(chat_id):
        await responder(update, textos.ayuda_usuario(len(nombres), nombres))
        return
    await responder(update, textos.NO_AUTORIZADO)


# ---------------------------------------------------------------------------
# Red de seguridad: aqui nunca puede haber silencio
# ---------------------------------------------------------------------------


async def comando_desconocido(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cualquier comando que no exista. Sin esto el bot se queda mudo y el
    usuario cree que esta roto."""
    if not acceso.esta_autorizado(update.effective_chat.id):
        await responder(update, textos.NO_AUTORIZADO)
        return
    await responder(update, textos.COMANDO_DESCONOCIDO)


async def contenido_no_soportado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Videos, stickers, ubicaciones y demas. Nunca dejar al usuario sin respuesta."""
    if not acceso.esta_autorizado(update.effective_chat.id):
        await responder(update, textos.NO_AUTORIZADO)
        return
    await responder(update, textos.FORMATO_NO_SOPORTADO)


# ---------------------------------------------------------------------------
# Texto libre
# ---------------------------------------------------------------------------


async def mensaje_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Un texto de alguien sin autorizar se interpreta como intento de codigo.

    No hace falta guardar en que paso va cada usuario: si no esta autorizado,
    lo unico que puede querer es entrar. Menos estado, menos fallos.
    """
    chat_id = update.effective_chat.id
    nombre = update.effective_user.full_name if update.effective_user else ""
    texto = update.effective_message.text or ""

    if acceso.esta_autorizado(chat_id):
        # Un boton del menu manda su etiqueta como texto. Se atiende como
        # comando, no como pregunta para Claude.
        if await comandos.pulsacion_de_boton(update, context):
            return
        await comandos.atender_pregunta(update, context, texto)
        return

    if not almacen.leer_config().get("codigo_hash"):
        await responder(update, textos.BOT_SIN_PREPARAR)
        return

    # El bloqueo se comprueba antes de mirar el codigo, o no serviria de nada.
    if limites.esta_bloqueado(chat_id):
        await responder(update, textos.estas_bloqueado(
            limites.minutos_de_bloqueo(chat_id)
        ))
        return

    if acceso.codigo_correcto(texto):
        await limites.perdonar(chat_id)
        await acceso.autorizar(chat_id, nombre)
        log.info("Acceso concedido a %s (%s)", chat_id, nombre)
        await _dar_la_bienvenida(update, context, chat_id)
        return

    await almacen.registrar_evento("codigo_fallido", chat_id, nombre)
    restantes = await limites.registrar_fallo(chat_id)

    if restantes > 0:
        await responder(update, textos.codigo_incorrecto_con_avisos(restantes))
        return

    # Se acaba de bloquear. Al owner le interesa enterarse.
    await almacen.registrar_evento("bloqueo_intentos", chat_id, nombre)
    await responder(update, textos.estas_bloqueado(
        limites.minutos_de_bloqueo(chat_id)
    ))
    duenno = acceso.owner_id()
    if duenno is not None:
        try:
            await context.bot.send_message(
                duenno,
                textos.aviso_intentos_al_owner(nombre or f"Alguien ({chat_id})"),
                parse_mode="HTML",
            )
        except Exception:
            log.warning("No he podido avisar al owner del bloqueo")


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


async def manejar_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra el fallo tecnico y al usuario le decimos algo comprensible."""
    log.exception("Fallo procesando una actualizacion", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await responder(update, textos.ERROR_GENERICO)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------


def registrar_despacho() -> None:
    """Que ejecuta cada boton del teclado.

    Se rellena desde aqui para que comandos.py no tenga que importar los
    handlers que viven en este modulo. Hay una prueba que verifica que
    ningun boton se queda sin su handler.
    """
    comandos.DESPACHO.update({
        "doc": comandos.comando_doc,
        "docs": comandos.comando_docs,
        "borrar": comandos.comando_borrar,
        "costes": comandos.comando_costes,
        "usuarios": comandos.comando_usuarios,
        "logs": comandos.comando_logs,
        "backup": comandos.comando_backup,
        "codigo": comando_codigo,
        "ayuda": comando_ayuda,
    })


def main() -> None:
    faltan = ajustes.faltan_variables_obligatorias()
    if faltan:
        print(
            "No puedo arrancar porque faltan estas variables de entorno: "
            + ", ".join(faltan)
            + "\n\nEn local se ponen en el fichero .env.local.\n"
            "En Railway, en la pestana Variables del servicio.",
            file=sys.stderr,
        )
        sys.exit(1)

    almacen.inicializar()
    log.info(almacen.resumen_arranque())

    app = Application.builder().token(ajustes.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("ayuda", comando_ayuda))
    app.add_handler(CommandHandler("codigo", comando_codigo))
    app.add_handler(CommandHandler("doc", comandos.comando_doc))
    app.add_handler(CommandHandler("docs", comandos.comando_docs))
    app.add_handler(CommandHandler("borrar", comandos.comando_borrar))
    app.add_handler(CommandHandler("costes", comandos.comando_costes))
    app.add_handler(CommandHandler("limite", comandos.comando_limite))
    app.add_handler(CommandHandler("menu", comandos.comando_menu))
    app.add_handler(CommandHandler("usuarios", comandos.comando_usuarios))
    app.add_handler(CommandHandler("logs", comandos.comando_logs))
    app.add_handler(CommandHandler("backup", comandos.comando_backup))
    app.add_handler(CallbackQueryHandler(
        comandos.pulsacion_borrar, pattern=f"^{comandos.PREFIJO_BORRAR}"
    ))
    app.add_handler(CallbackQueryHandler(
        comandos.pulsacion_revocar, pattern=f"^{comandos.PREFIJO_REVOCAR}"
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_texto))
    app.add_handler(MessageHandler(filters.Document.ALL, comandos.recibir_documento))
    app.add_handler(MessageHandler(filters.PHOTO, comandos.recibir_foto))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, comandos.recibir_voz))
    # Todo lo demas que no sea texto: videos, stickers, ubicaciones.
    app.add_handler(MessageHandler(filters.ATTACHMENT, contenido_no_soportado))
    # Este va el ultimo a proposito: caza cualquier comando que no exista.
    app.add_handler(MessageHandler(filters.COMMAND, comando_desconocido))
    app.add_error_handler(manejar_error)
    registrar_despacho()

    log.info("Bot arrancado. Esperando mensajes.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
