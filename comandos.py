"""Comandos y recepción de ficheros.

Todo lo que el owner hace con su documentación: subirla, verla y quitarla.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import acceso
import ajustes
import almacen
import claude_api
import comun
import consulta
import copia
import costes
import extraccion
import limites
import menu
import textos
import web
from comun import documentos_cargados, escribiendo, responder, responder_largo

log = logging.getLogger("empleado.comandos")

PREFIJO_BORRAR = "borrar:"
CANCELAR_BORRAR = "borrar:__cancelar__"


def _coste_por_pregunta() -> str:
    caliente, _frio = costes.estimar_pregunta(almacen.total_tokens())
    return costes.en_euros(caliente)


# ---------------------------------------------------------------------------
# /doc y /docs
# ---------------------------------------------------------------------------


async def comando_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """No activa ningún modo: los ficheros del owner se aceptan siempre.

    Guardar un estado de "estoy esperando un fichero" solo serviría para que
    se quedara colgado. El comando es solo una explicación.
    """
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER_SUBE)
        return
    await responder(update, textos.PIDE_DOCUMENTOS)


async def comando_docs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.esta_autorizado(update.effective_chat.id):
        await responder(update, textos.NO_AUTORIZADO)
        return
    fichas = [
        (nombre, int(almacen.metadatos_de(nombre).get("tokens", 0)))
        for nombre in documentos_cargados()
    ]
    await responder(
        update,
        textos.lista_documentos(fichas, almacen.total_tokens(), _coste_por_pregunta()),
    )


# ---------------------------------------------------------------------------
# /borrar
# ---------------------------------------------------------------------------


async def comando_borrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER)
        return

    nombres = documentos_cargados()
    if not nombres:
        await responder(update, textos.lista_documentos([], 0, ""))
        return

    # Un botón por documento y uno para salir sin tocar nada. Los nombres
    # están saneados a 40 caracteres, así que el callback_data cabe de sobra
    # en los 64 bytes que permite Telegram.
    botones = [
        [InlineKeyboardButton(nombre, callback_data=f"{PREFIJO_BORRAR}{nombre}")]
        for nombre in nombres
    ]
    botones.append([InlineKeyboardButton("Dejarlo como está", callback_data=CANCELAR_BORRAR)])
    await update.effective_message.reply_text(
        textos.ELIGE_DOCUMENTO_A_BORRAR,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botones),
    )


async def pulsacion_borrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pulsacion = update.callback_query
    await pulsacion.answer()

    if not acceso.es_owner(pulsacion.message.chat.id):
        await pulsacion.edit_message_text(textos.SOLO_OWNER)
        return

    if pulsacion.data == CANCELAR_BORRAR:
        await pulsacion.edit_message_text(textos.BORRADO_CANCELADO)
        return

    nombre = pulsacion.data[len(PREFIJO_BORRAR):]
    if not await almacen.borrar_documento(nombre):
        # Puede pasar si el owner pulsa dos veces o borra desde otro chat.
        await pulsacion.edit_message_text(textos.BORRADO_CANCELADO)
        return

    await almacen.registrar_evento("documento_borrado", pulsacion.message.chat.id, nombre)
    consulta.olvidar_todo()
    quedan = len(documentos_cargados())
    await pulsacion.edit_message_text(
        textos.documento_borrado(nombre, quedan), parse_mode="HTML"
    )
    await copia_automatica_si_toca(context)


# ---------------------------------------------------------------------------
# Recepción de ficheros
# ---------------------------------------------------------------------------


async def _descargar(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    fichero = await context.bot.get_file(file_id)
    return bytes(await fichero.download_as_bytearray())


async def _guardar_y_responder(
    update: Update, nombre_original: str, documento: extraccion.Documento
) -> None:
    """Cuenta tokens, guarda y le cuenta al owner lo que le va a costar."""
    nombre = extraccion.sanear_nombre(nombre_original)
    tokens = await claude_api.contar_tokens(documento.texto)
    sobrescrito = await almacen.guardar_documento(
        nombre, documento.texto, tokens, documento.origen
    )
    consulta.olvidar_todo()

    # Leer un escaneado o una foto cuesta dinero, así que se contabiliza.
    if documento.uso is not None:
        await costes.registrar_uso(documento.uso, f"extraccion:{documento.origen}")

    await almacen.registrar_evento(
        "documento_guardado", update.effective_chat.id, f"{nombre} ({tokens} tokens)"
    )

    total = almacen.total_tokens()
    await responder(update, textos.documento_guardado(
        nombre=nombre,
        tokens=tokens,
        total_documentos=len(documentos_cargados()),
        total_tokens=total,
        coste_caliente=_coste_por_pregunta(),
        sobrescrito=sobrescrito,
        avisos=documento.avisos,
    ))

    await _avisar_si_documentacion_grande(update)


async def _avisar_si_documentacion_grande(update: Update) -> None:
    """Aviso de coste una sola vez, cuando se cruza el umbral."""
    total = almacen.total_tokens()
    config = almacen.leer_config()
    if total > ajustes.AVISO_TOKENS_DOCUMENTOS and config.get("avisado_tokens") != "si":
        await almacen.actualizar_config(avisado_tokens="si")
        await responder(update, textos.aviso_documentacion_grande(total, _coste_por_pregunta()))


async def recibir_documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mensaje = update.effective_message
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER_SUBE)
        return

    fichero = mensaje.document
    if fichero.file_size and fichero.file_size > ajustes.MAX_BYTES_DESCARGA:
        await responder(update, textos.FICHERO_DEMASIADO_GRANDE)
        return

    nombre = fichero.file_name or "documento"
    if extraccion.extension_de(nombre) not in extraccion.EXTENSIONES_ACEPTADAS:
        if extraccion.extension_de(nombre) != ".doc":
            await responder(update, textos.FORMATO_NO_SOPORTADO)
            return

    async with escribiendo(update):
        await responder(update, textos.LEYENDO)
        try:
            datos = await _descargar(context, fichero.file_id)
            documento = await extraccion.extraer_fichero(nombre, datos)
            await _guardar_y_responder(update, nombre, documento)
            await copia_automatica_si_toca(context)
        except extraccion.ErrorExtraccion as error:
            await responder(update, textos.no_he_podido_leer(str(error)))
        except claude_api.ProblemaConClaude as error:
            # Subir un documento llama a Claude para contar los tokens, asi
            # que aqui es donde se nota por primera vez que la clave esta mal
            # o que no hay saldo. Merece un mensaje que diga qué hacer.
            log.warning("Subida fallida por la API: %s", error.motivo)
            await responder(update, textos.problema_al_subir(error.motivo))
        except Exception:
            log.exception("Fallo procesando %s", nombre)
            await responder(update, textos.ERROR_GENERICO)


async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER_SUBE)
        return

    # Telegram manda varias resoluciones. La última es la más grande.
    foto = update.effective_message.photo[-1]
    nombre = update.effective_message.caption or f"foto_{foto.file_unique_id}"

    async with escribiendo(update):
        await responder(update, textos.LEYENDO)
        try:
            datos = await _descargar(context, foto.file_id)
            documento = await extraccion.extraer_imagen(datos, "image/jpeg")
            await _guardar_y_responder(update, nombre, documento)
            await copia_automatica_si_toca(context)
        except extraccion.ErrorExtraccion as error:
            await responder(update, textos.no_he_podido_leer(str(error)))
        except claude_api.ProblemaConClaude as error:
            log.warning("Foto fallida por la API: %s", error.motivo)
            await responder(update, textos.problema_al_subir(error.motivo))
        except Exception:
            log.exception("Fallo procesando una foto")
            await responder(update, textos.ERROR_GENERICO)


async def recibir_voz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Una nota de voz es una pregunta, no un documento.

    Se transcribe y se trata igual que si la hubiera escrito. En esta fase
    todavía no hay consulta, así que se le enseña lo que se ha entendido.
    """
    if not acceso.esta_autorizado(update.effective_chat.id):
        await responder(update, textos.NO_AUTORIZADO)
        return

    if not claude_api.hay_transcripcion():
        await responder(update, textos.VOZ_SIN_CONFIGURAR)
        return

    voz = update.effective_message.voice or update.effective_message.audio
    if voz.file_size and voz.file_size > ajustes.MAX_BYTES_DESCARGA:
        await responder(update, textos.FICHERO_DEMASIADO_GRANDE)
        return

    async with escribiendo(update):
        await responder(update, textos.ESCUCHANDO)
        try:
            datos = await _descargar(context, voz.file_id)
            documento = await extraccion.transcribir(datos)
        except extraccion.ErrorExtraccion as error:
            await responder(update, textos.no_he_podido_leer(str(error)))
            return
        except Exception:
            log.exception("Fallo transcribiendo una nota de voz")
            await responder(update, textos.VOZ_HA_FALLADO)
            return

    # Se le enseña lo que se ha entendido antes de contestar, para que pueda
    # corregir si la transcripción no era lo que quería decir.
    await responder(update, textos.voz_entendida(documento.texto))
    await atender_pregunta(update, context, documento.texto)


# ---------------------------------------------------------------------------
# Páginas web
# ---------------------------------------------------------------------------


async def recibir_webs_si_toca(
    update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str
) -> bool:
    """Si el mensaje solo trae direcciones, se leen. Devuelve si lo ha atendido.

    No hay comando ni modo: pegar direcciones ya es pedir que se lean. Un
    mensaje que además trae otras palabras es una pregunta y sigue su camino.
    """
    direcciones = web.direcciones_del_mensaje(texto)
    if not direcciones:
        return False

    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER_WEBS)
        return True

    if len(direcciones) > web.MAX_DIRECCIONES:
        await responder(update, textos.demasiadas_direcciones(web.MAX_DIRECCIONES))
        return True

    await responder(update, textos.leyendo_webs(len(direcciones)))
    guardada_alguna = False
    for direccion in direcciones:
        async with escribiendo(update):
            try:
                guardada_alguna |= await _leer_y_guardar_web(update, direccion)
            except web.WebNoLeida as error:
                log.info("Web no leida (%s): %s", error.motivo, direccion)
                await responder(update, textos.web_no_leida(direccion, error.motivo))
            except claude_api.ProblemaConClaude as error:
                log.warning("Web fallida por la API: %s", error.motivo)
                await responder(update, textos.problema_al_subir(error.motivo))
                # Si falla la clave o el saldo, fallarán todas. Mejor parar.
                break
            except Exception:
                log.exception("Fallo leyendo %s", direccion)
                await responder(update, textos.web_no_leida(direccion, "no_responde"))

    if guardada_alguna:
        await _avisar_si_documentacion_grande(update)
        await copia_automatica_si_toca(context)
    return True


async def _leer_y_guardar_web(update: Update, direccion: str) -> bool:
    """Lee la página, la resume y la guarda. Devuelve si la ha guardado."""
    pagina = await web.leer_pagina(direccion)
    valida, resumen, uso = await claude_api.resumir_web(pagina.documento.texto)
    await costes.registrar_uso(uso, "resumen:web")
    if pagina.documento.uso is not None:
        await costes.registrar_uso(pagina.documento.uso, "extraccion:web")

    if not valida:
        await responder(update, textos.web_sin_contenido(pagina.direccion, resumen))
        return False

    nombre = web.nombre_para(pagina.direccion)
    tokens = await claude_api.contar_tokens(pagina.documento.texto)
    sobrescrito = await almacen.guardar_documento(
        nombre, pagina.documento.texto, tokens, "web"
    )
    consulta.olvidar_todo()
    await almacen.registrar_evento(
        "web_guardada", update.effective_chat.id, f"{nombre} ({tokens} tokens) {pagina.direccion}"
    )

    # El botón reutiliza el de /borrar, que no guarda nada entre mensajes.
    boton = InlineKeyboardMarkup([[InlineKeyboardButton(
        textos.BOTON_QUITAR_WEB, callback_data=f"{PREFIJO_BORRAR}{nombre}"
    )]])
    await update.effective_message.reply_text(
        textos.web_guardada(
            nombre=nombre,
            direccion=pagina.direccion,
            titulo=pagina.titulo,
            resumen=resumen,
            tokens=tokens,
            total_documentos=len(documentos_cargados()),
            coste_caliente=_coste_por_pregunta(),
            sobrescrito=sobrescrito,
        ),
        parse_mode="HTML",
        reply_markup=boton,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    return True


# ---------------------------------------------------------------------------
# Preguntas
# ---------------------------------------------------------------------------


async def atender_pregunta(
    update: Update, context: ContextTypes.DEFAULT_TYPE, pregunta: str
) -> None:
    """Consulta la documentación y responde, venga de texto o de una voz."""
    chat_id = update.effective_chat.id
    es_owner = acceso.es_owner(chat_id)

    # El tope por hora protege el presupuesto de un usuario que se emociona.
    # El owner queda fuera: es su dinero y su bot.
    if not es_owner and limites.ha_pasado_del_limite(chat_id):
        await responder(update, textos.demasiadas_preguntas(
            limites.minutos_hasta_poder_preguntar(chat_id)
        ))
        return

    respuesta = ""
    async with escribiendo(update):
        try:
            respuesta, _uso = await consulta.preguntar(chat_id, pregunta)
        except consulta.SinDocumentacion:
            await responder(update, (
                textos.SIN_DOCUMENTACION_OWNER
                if es_owner
                else textos.SIN_DOCUMENTACION_EMPLEADO
            ))
            return
        except consulta.LimiteAlcanzado:
            await _contar_que_se_acabo(update, context, es_owner)
            return
        except consulta.ProblemaConClaude as error:
            log.warning("Consulta fallida: %s", error.motivo)
            await responder(update, textos.problema_al_responder(error.motivo))
            return
        except Exception:
            log.exception("Fallo inesperado atendiendo una pregunta")
            await responder(update, textos.ERROR_GENERICO)
            return

    await limites.registrar_pregunta(chat_id)

    if not respuesta.strip():
        await responder(update, textos.RESPUESTA_VACIA)
    else:
        await responder_largo(update, respuesta)

    await _avisar_al_owner_si_toca(context)


async def _contar_que_se_acabo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, es_owner: bool
) -> None:
    """Al owner se le explica qué hacer. Al empleado, a quién avisar."""
    gastado = costes.en_euros(costes.gasto_del_mes())
    if es_owner:
        await responder(update, textos.tope_alcanzado_owner(
            gastado, costes.limite_mensual()
        ))
    else:
        await responder(update, textos.tope_alcanzado_usuario(
            almacen.leer_config().get("nombre_empresa", "")
        ))
        await _avisar_al_owner_si_toca(context)


async def _avisar_al_owner_si_toca(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Avisos de gasto al owner, una sola vez cada uno por mes."""
    destino = acceso.owner_id()
    if destino is None:
        return

    if costes.hay_que_avisar_del_100():
        await costes.marcar_avisado("avisado_100")
        await _mandar_al_owner(context, destino, textos.tope_alcanzado_owner(
            costes.en_euros(costes.gasto_del_mes()),
            costes.limite_mensual(),
        ))
        return

    if costes.hay_que_avisar_del_80():
        await costes.marcar_avisado("avisado_80")
        await _mandar_al_owner(context, destino, textos.aviso_80_por_ciento(
            costes.en_euros(costes.gasto_del_mes()),
            costes.limite_mensual(),
            costes.en_euros(costes.proyeccion_fin_de_mes()),
        ))


async def _mandar_al_owner(
    context: ContextTypes.DEFAULT_TYPE, destino: int, texto: str
) -> None:
    """Si el owner nunca ha hablado con el bot, Telegram no deja escribirle.

    No es motivo para romper nada, así que se registra y se sigue.
    """
    try:
        await context.bot.send_message(destino, texto, parse_mode="HTML")
    except Exception:
        log.warning("No he podido avisar al owner (%s)", destino)


# ---------------------------------------------------------------------------
# /costes y /limite
# ---------------------------------------------------------------------------


async def comando_costes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER)
        return

    datos = costes.datos_del_mes()
    caliente, _frio = costes.estimar_pregunta(almacen.total_tokens())
    await responder(update, textos.informe_de_costes(
        gastado=costes.en_euros(costes.gasto_del_mes()),
        limite_dolares=costes.limite_mensual(),
        porcentaje=int(costes.porcentaje_gastado() * 100),
        preguntas=int(datos.get("peticiones", 0)),
        coste_pregunta=costes.en_euros(caliente),
        proyeccion=costes.en_euros(costes.proyeccion_fin_de_mes()),
        documentos=len(documentos_cargados()),
        tokens=costes.con_miles(almacen.total_tokens()),
    ))


async def comando_limite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER)
        return

    if not context.args:
        await responder(update, textos.LIMITE_MAL_ESCRITO)
        return
    try:
        nuevo = float(context.args[0].replace(",", ".").replace("$", "").strip())
    except ValueError:
        await responder(update, textos.LIMITE_MAL_ESCRITO)
        return
    if nuevo < 1:
        await responder(update, textos.LIMITE_DEMASIADO_BAJO)
        return

    await costes.cambiar_limite(nuevo)
    # Si sube el tope por encima de lo gastado, los avisos vuelven a servir.
    if costes.porcentaje_gastado() < costes.UMBRAL_AVISO:
        datos = costes.datos_del_mes()
        datos["avisado_80"] = False
        datos["avisado_100"] = False
        await almacen.guardar_json(almacen.FICHERO_USO, datos)

    await almacen.registrar_evento("limite_cambiado", update.effective_chat.id, str(nuevo))
    await responder(update, textos.limite_cambiado(
        nuevo, costes.en_euros(costes.gasto_del_mes())
    ))


# ---------------------------------------------------------------------------
# Botones
# ---------------------------------------------------------------------------


async def comando_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not acceso.esta_autorizado(chat_id):
        await responder(update, textos.NO_AUTORIZADO)
        return
    await update.effective_message.reply_text(
        textos.MENU_AQUI,
        reply_markup=menu.teclado_para(acceso.es_owner(chat_id)),
    )


# ---------------------------------------------------------------------------
# /usuarios
# ---------------------------------------------------------------------------

PREFIJO_REVOCAR = "revocar:"
CANCELAR_REVOCAR = "revocar:__cancelar__"


async def comando_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER)
        return

    gente = acceso.autorizados()
    if not gente:
        await responder(update, textos.lista_de_usuarios([]))
        return

    resumen = [
        (datos.get("nombre") or f"Chat {identificador}",
         comun.hora_local(datos.get("desde", "")))
        for identificador, datos in sorted(gente.items())
    ]
    botones = [
        [InlineKeyboardButton(
            f"Quitar acceso a {datos.get('nombre') or identificador}",
            callback_data=f"{PREFIJO_REVOCAR}{identificador}",
        )]
        for identificador, datos in sorted(gente.items())
    ]
    botones.append([InlineKeyboardButton("Dejarlo como está", callback_data=CANCELAR_REVOCAR)])
    await update.effective_message.reply_text(
        textos.lista_de_usuarios(resumen),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botones),
    )


async def pulsacion_revocar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pulsacion = update.callback_query
    await pulsacion.answer()

    if not acceso.es_owner(pulsacion.message.chat.id):
        await pulsacion.edit_message_text(textos.SOLO_OWNER)
        return

    if pulsacion.data == CANCELAR_REVOCAR:
        await pulsacion.edit_message_text(textos.REVOCAR_CANCELADO)
        return

    try:
        identificador = int(pulsacion.data[len(PREFIJO_REVOCAR):])
    except ValueError:
        await pulsacion.edit_message_text(textos.NADIE_A_QUIEN_QUITAR)
        return

    nombre = acceso.autorizados().get(identificador, {}).get("nombre", str(identificador))
    if not await acceso.revocar(identificador):
        await pulsacion.edit_message_text(textos.NADIE_A_QUIEN_QUITAR)
        return

    # Que deje de responderle en mitad de una conversacion seria raro, asi
    # que tambien se le olvida el hilo.
    consulta.olvidar(identificador)
    await pulsacion.edit_message_text(
        textos.acceso_revocado(nombre or str(identificador)), parse_mode="HTML"
    )


# ---------------------------------------------------------------------------
# /logs
# ---------------------------------------------------------------------------


async def comando_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER)
        return
    lineas = [
        comun.formatear_evento(linea)
        for linea in almacen.ultimos_eventos(20)
        if linea.strip()
    ]
    await responder(update, textos.registro_de_accesos(lineas))


# ---------------------------------------------------------------------------
# /backup
# ---------------------------------------------------------------------------


async def comando_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not acceso.es_owner(update.effective_chat.id):
        await responder(update, textos.SOLO_OWNER)
        return
    if not documentos_cargados():
        await responder(update, textos.COPIA_SIN_NADA)
        return

    await responder(update, textos.COPIA_PREPARANDO)
    async with escribiendo(update, ChatAction.UPLOAD_DOCUMENT):
        nombre, datos = await copia.construir()
        await update.effective_message.reply_document(
            document=datos, filename=nombre,
            caption=textos.COPIA_MANUAL, parse_mode="HTML",
        )
    await copia.marcar_copia_hecha()
    await almacen.registrar_evento("copia_enviada", update.effective_chat.id, "a mano")


async def copia_automatica_si_toca(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manda la copia al owner cuando ha cambiado la documentación.

    Como mucho una al día. Un backup que hay que acordarse de pedir no salva
    a nadie, y este se queda en el chat para siempre.
    """
    if not copia.toca_copia_automatica():
        return
    destino = acceso.owner_id()
    if destino is None:
        return
    try:
        nombre, datos = await copia.construir()
        await context.bot.send_document(
            destino, document=datos, filename=nombre,
            caption=textos.COPIA_AUTOMATICA, parse_mode="HTML",
        )
    except Exception:
        log.warning("No he podido mandar la copia automatica al owner")
        return
    await copia.marcar_copia_hecha()
    await almacen.registrar_evento("copia_enviada", destino, "automatica")


# Que comando ejecuta cada boton. Se rellena desde bot.py al arrancar para
# no tener que importar aqui los handlers que viven alli.
DESPACHO: dict[str, object] = {}


async def pulsacion_de_boton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Si el texto es un botón, lo ejecuta y devuelve True.

    Sin esto, pulsar un botón mandaría su etiqueta a Claude como pregunta.
    """
    texto = (update.effective_message.text or "").strip()
    nombre = menu.comando_de(texto)
    if not nombre:
        return False
    manejador = DESPACHO.get(nombre)
    if manejador is None:
        return False
    await manejador(update, context)
    return True
