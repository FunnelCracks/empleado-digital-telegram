"""Tu Empleado Digital: arranque del bot y registro de handlers.

Aqui solo viven el arranque, los handlers de entrada y el reparto. La logica
de cada cosa esta en su modulo.
"""

import logging
import sys

from telegram import Update
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
import modo
import textos
from comun import (
    documentos_cargados,
    registrar_comandos,
    responder,
    responder_no_permitido,
)

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

    # Caso 1: ya es el administrador. Si todavía no ha elegido para quién es
    # el bot (o se fijó OWNER_CHAT_ID por variable y es su primera vez), se
    # le pide ahora.
    if acceso.es_owner(chat_id):
        if acceso.modo() is None:
            await responder(update, textos.ALTA_OWNER)
            await modo.ensenar_eleccion(update)
            return
        para_clientes = acceso.es_modo_clientes()
        await update.effective_message.reply_text(
            textos.owner_vuelve(cuantos_documentos()),
            parse_mode="HTML",
            reply_markup=menu.teclado_owner(para_clientes),
        )
        await registrar_comandos(context, chat_id, es_owner=True, para_clientes=para_clientes)
        return

    # Caso 2: no hay administrador todavia y el registro automatico esta
    # activo, asi que el primero que escribe se queda con el bot. Lo primero
    # que tiene que hacer es elegir para quién es. El código de acceso, si lo
    # hay, sale después.
    if not acceso.hay_owner() and acceso.registro_automatico_activo():
        await acceso.registrar_owner(chat_id, nombre)
        log.info("Alta de owner: %s (%s)", chat_id, nombre)
        await responder(update, textos.ALTA_OWNER)
        await modo.ensenar_eleccion(update)
        return

    # Caso 3: el administrador aún no ha elegido para quién es el bot. Hasta
    # entonces no se atiende a nadie más.
    actual = acceso.modo()
    if actual is None:
        await responder(update, textos.BOT_SIN_PREPARAR)
        return

    # Caso 4: un bot para clientes. Sin código, sin registrar a nadie.
    if actual == acceso.MODO_CLIENTES:
        await update.effective_message.reply_text(
            textos.bienvenida_cliente(almacen.leer_config().get("nombre_empresa", "")),
            parse_mode="HTML",
            reply_markup=menu.teclado_cliente(),
        )
        await registrar_comandos(context, chat_id, es_owner=False, para_clientes=True)
        return

    # Caso 5: bot de equipo sin código puesto. No debería pasar, porque el
    # código se crea al elegir el modo, pero no se deja entrar a nadie.
    if not almacen.leer_config().get("codigo_hash"):
        await responder(update, textos.BOT_SIN_PREPARAR)
        return

    # Caso 6: empleado ya autorizado.
    if acceso.esta_autorizado(chat_id):
        await _dar_la_bienvenida(update, context, chat_id)
        return

    # Caso 7: alguien nuevo. Le pedimos el codigo.
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


# ---------------------------------------------------------------------------
# /codigo
# ---------------------------------------------------------------------------


async def comando_codigo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not acceso.es_owner(chat_id):
        await responder_no_permitido(update, textos.SOLO_OWNER)
        return
    if acceso.es_modo_clientes():
        await responder(update, textos.CODIGO_NO_EN_CLIENTES)
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
        await responder(update, textos.ayuda_owner(
            len(nombres), nombres, para_clientes=acceso.es_modo_clientes()
        ))
        return
    if acceso.es_cliente(chat_id):
        await responder(update, textos.ayuda_cliente(
            almacen.leer_config().get("nombre_empresa", "")
        ))
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
    if acceso.es_cliente(update.effective_chat.id):
        await responder(update, textos.COMANDO_DESCONOCIDO_CLIENTE)
        return
    if not acceso.esta_autorizado(update.effective_chat.id):
        await responder(update, textos.NO_AUTORIZADO)
        return
    await responder(update, textos.COMANDO_DESCONOCIDO)


async def contenido_no_soportado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Videos, stickers, ubicaciones y demas. Nunca dejar al usuario sin respuesta."""
    if acceso.es_cliente(update.effective_chat.id):
        await responder(update, textos.SOLO_TEXTO_CLIENTE)
        return
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

    # El administrador tiene que elegir para quién es el bot antes de nada.
    if acceso.es_owner(chat_id) and acceso.modo() is None:
        await responder(update, textos.ELIGE_MODO_PRIMERO)
        await modo.ensenar_eleccion(update)
        return

    if acceso.puede_preguntar(chat_id):
        # La respuesta a /empresa o /contacto no es una pregunta.
        if await modo.respuesta_de_empresa_si_toca(update, context):
            return
        # Un boton del menu manda su etiqueta como texto. Se atiende como
        # comando, no como pregunta para Claude.
        if await comandos.pulsacion_de_boton(update, context):
            return
        if await comandos.recibir_webs_si_toca(update, context, texto):
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
        "empresa": modo.comando_empresa,
        "enlace": modo.comando_enlace,
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
    app.add_handler(CommandHandler("empresa", modo.comando_empresa))
    app.add_handler(CommandHandler("contacto", modo.comando_contacto))
    app.add_handler(CommandHandler("enlace", modo.comando_enlace))
    app.add_handler(CallbackQueryHandler(modo.pulsacion_modo, pattern=f"^{modo.PREFIJO_MODO}"))
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
