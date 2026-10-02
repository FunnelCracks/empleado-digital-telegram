"""Pruebas del modo del bot: para el equipo o para los clientes.

Lo primero que se comprueba es la seguridad: que el modo no se puede
cambiar una vez elegido, que un cliente no llega a nada de administración y
que en un bot para clientes no se guarda nada de quien escribe.

Sin red: Telegram y Claude se sustituyen por dobles.

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_TEMPORAL = Path(tempfile.mkdtemp(prefix="empleado_pruebas_"))
os.environ["RUTA_DATOS"] = str(_TEMPORAL)
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-prueba")
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-de-prueba")
os.environ["OWNER_CHAT_ID"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import acceso  # noqa: E402
import ajustes  # noqa: E402
import almacen  # noqa: E402
import bot  # noqa: E402
import comandos  # noqa: E402
import consulta  # noqa: E402
import costes  # noqa: E402
import limites  # noqa: E402
import modo  # noqa: E402
import textos  # noqa: E402

JEFE = 1111
CLIENTE = 3333
OTRO_CLIENTE = 4444


def limpiar_volume() -> None:
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)
    almacen.inicializar()
    consulta._historiales.clear()


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


# ---------------------------------------------------------------------------
# Dobles de Telegram
# ---------------------------------------------------------------------------


class MensajeFalso:
    def __init__(self, texto: str = "", chat_id: int = 0, respuesta_a=None) -> None:
        self.text = texto
        self.chat = SimpleNamespace(id=chat_id)
        self.reply_to_message = respuesta_a
        self.document = None
        self.photo = []
        self.voice = None
        self.audio = None
        self.enviados: list[dict] = []

    async def reply_text(self, texto: str, **opciones) -> None:
        self.enviados.append({"texto": texto, **opciones})

    async def reply_document(self, **opciones) -> None:
        self.enviados.append({"texto": "<documento>", **opciones})


class PulsacionFalsa:
    def __init__(self, datos: str, chat_id: int) -> None:
        self.data = datos
        self.message = MensajeFalso(chat_id=chat_id)
        self.editados: list[dict] = []

    async def answer(self) -> None:
        return None

    async def edit_message_text(self, texto: str, **opciones) -> None:
        self.editados.append({"texto": texto, **opciones})


class BotFalso:
    username = "cartonajes_bot"

    def __init__(self) -> None:
        self.mandados: list[tuple[int, str]] = []

    async def set_my_commands(self, *args, **kwargs) -> None:
        return None

    async def send_message(self, destino: int, texto: str, **opciones) -> None:
        self.mandados.append((destino, texto))

    async def send_chat_action(self, *args, **kwargs) -> None:
        return None


def update_de(chat_id: int, texto: str = "", respuesta_a=None, nombre: str = "Fulano"):
    mensaje = MensajeFalso(texto, chat_id, respuesta_a)
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(full_name=nombre),
        effective_message=mensaje,
        callback_query=None,
    )


def pulsacion_de(chat_id: int, datos: str):
    pulsacion = PulsacionFalsa(datos, chat_id)
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(full_name="Jefa"),
        effective_message=pulsacion.message,
        callback_query=pulsacion,
    )


def contexto(args: list[str] | None = None):
    return SimpleNamespace(bot=BotFalso(), args=args or [])


def textos_enviados(update) -> list[str]:
    return [envio["texto"] for envio in update.effective_message.enviados]


async def montar(elegido: str | None) -> None:
    """Un bot con el jefe dado de alta y, si se pide, el modo ya elegido."""
    limpiar_volume()
    await acceso.registrar_owner(JEFE, "Jefa")
    if elegido == acceso.MODO_EQUIPO:
        await acceso.fijar_modo(acceso.MODO_EQUIPO)
        await acceso.establecer_codigo_nuevo()
    elif elegido == acceso.MODO_CLIENTES:
        await acceso.fijar_modo(acceso.MODO_CLIENTES)


class UsoFalso:
    def __init__(self, entrada: int = 0, salida: int = 0) -> None:
        self.input_tokens = entrada
        self.output_tokens = salida
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class SinEscribiendo:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *error) -> None:
        return None


# ---------------------------------------------------------------------------
# El modo en sí
# ---------------------------------------------------------------------------


class ElModo(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_un_bot_nuevo_no_tiene_modo(self) -> None:
        await acceso.registrar_owner(JEFE, "Jefa")
        self.assertIsNone(acceso.modo())

    async def test_los_bots_de_antes_son_de_equipo(self) -> None:
        """Ya tienen código y ningún modo guardado: siguen igual que siempre."""
        await acceso.registrar_owner(JEFE, "Jefa")
        await acceso.establecer_codigo_nuevo()
        self.assertEqual(acceso.modo(), acceso.MODO_EQUIPO)
        self.assertFalse(await acceso.fijar_modo(acceso.MODO_CLIENTES))
        self.assertEqual(acceso.modo(), acceso.MODO_EQUIPO)

    async def test_se_elige_una_sola_vez(self) -> None:
        self.assertTrue(await acceso.fijar_modo(acceso.MODO_CLIENTES))
        self.assertFalse(await acceso.fijar_modo(acceso.MODO_EQUIPO))
        self.assertFalse(await acceso.fijar_modo(acceso.MODO_CLIENTES))
        self.assertEqual(acceso.modo(), acceso.MODO_CLIENTES)

    async def test_dos_pulsaciones_a_la_vez_solo_gana_una(self) -> None:
        resultados = await asyncio.gather(
            acceso.fijar_modo(acceso.MODO_EQUIPO),
            acceso.fijar_modo(acceso.MODO_CLIENTES),
            acceso.fijar_modo(acceso.MODO_EQUIPO),
        )
        self.assertEqual(sum(resultados), 1)

    async def test_un_modo_inventado_no_vale(self) -> None:
        self.assertFalse(await acceso.fijar_modo("todos"))
        self.assertIsNone(acceso.modo())

    async def test_quien_puede_preguntar(self) -> None:
        await acceso.registrar_owner(JEFE, "Jefa")
        # Sin modo: solo el jefe.
        self.assertTrue(acceso.puede_preguntar(JEFE))
        self.assertFalse(acceso.puede_preguntar(CLIENTE))
        # Para clientes: cualquiera.
        await acceso.fijar_modo(acceso.MODO_CLIENTES)
        self.assertTrue(acceso.puede_preguntar(CLIENTE))
        self.assertTrue(acceso.es_cliente(CLIENTE))
        self.assertFalse(acceso.es_cliente(JEFE))

    async def test_en_equipo_solo_con_codigo(self) -> None:
        await montar(acceso.MODO_EQUIPO)
        self.assertFalse(acceso.puede_preguntar(CLIENTE))
        self.assertFalse(acceso.es_cliente(CLIENTE))
        await acceso.autorizar(CLIENTE, "Empleado")
        self.assertTrue(acceso.puede_preguntar(CLIENTE))


# ---------------------------------------------------------------------------
# Elegir con los botones
# ---------------------------------------------------------------------------


class ElegirConBotones(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_el_primer_start_registra_al_jefe_y_pregunta_el_modo(self) -> None:
        update = update_de(JEFE, "/start")
        await bot.comando_start(update, contexto())
        self.assertTrue(acceso.es_owner(JEFE))
        self.assertIn(textos.ELEGIR_MODO, textos_enviados(update))
        # Todavía no hay código: solo existe si elige equipo.
        self.assertFalse(almacen.leer_config().get("codigo_hash"))

    async def test_antes_de_elegir_no_entra_nadie_mas(self) -> None:
        await bot.comando_start(update_de(JEFE, "/start"), contexto())
        update = update_de(CLIENTE, "/start")
        await bot.comando_start(update, contexto())
        self.assertEqual(textos_enviados(update), [textos.BOT_SIN_PREPARAR])

    async def test_si_el_jefe_escribe_sin_elegir_se_le_recuerda(self) -> None:
        await bot.comando_start(update_de(JEFE, "/start"), contexto())
        update = update_de(JEFE, "¿Cuánto cuesta la caja?")
        await bot.mensaje_texto(update, contexto())
        self.assertIn(textos.ELIGE_MODO_PRIMERO, textos_enviados(update))
        self.assertIn(textos.ELEGIR_MODO, textos_enviados(update))

    async def test_elegir_pide_confirmacion_y_no_fija_nada(self) -> None:
        await montar(None)
        pulsacion = pulsacion_de(JEFE, f"{modo.ELEGIR}{acceso.MODO_CLIENTES}")
        await modo.pulsacion_modo(pulsacion, contexto())
        self.assertIsNone(acceso.modo())
        self.assertEqual(
            pulsacion.callback_query.editados[-1]["texto"],
            textos.confirmar_modo(acceso.MODO_CLIENTES),
        )

    async def test_confirmar_clientes(self) -> None:
        await montar(None)
        pulsacion = pulsacion_de(JEFE, f"{modo.CONFIRMAR}{acceso.MODO_CLIENTES}")
        await modo.pulsacion_modo(pulsacion, contexto())
        self.assertEqual(acceso.modo(), acceso.MODO_CLIENTES)
        enviados = textos_enviados(pulsacion)
        self.assertIn(textos.AVISO_DATOS_CLIENTES, enviados)
        self.assertIn(textos.PREGUNTA_NOMBRE_EMPRESA, enviados)
        self.assertTrue(any("https://t.me/cartonajes_bot" in texto for texto in enviados))
        # En un bot para clientes no hay código.
        self.assertFalse(almacen.leer_config().get("codigo_hash"))

    async def test_confirmar_equipo_da_el_codigo(self) -> None:
        await montar(None)
        pulsacion = pulsacion_de(JEFE, f"{modo.CONFIRMAR}{acceso.MODO_EQUIPO}")
        await modo.pulsacion_modo(pulsacion, contexto())
        self.assertEqual(acceso.modo(), acceso.MODO_EQUIPO)
        self.assertTrue(almacen.leer_config().get("codigo_hash"))
        self.assertIn(textos.AVISO_DATOS, textos_enviados(pulsacion))

    async def test_un_boton_viejo_no_cambia_el_modo(self) -> None:
        await montar(acceso.MODO_CLIENTES)
        for datos in (
            f"{modo.CONFIRMAR}{acceso.MODO_EQUIPO}",
            f"{modo.ELEGIR}{acceso.MODO_EQUIPO}",
            modo.VOLVER,
        ):
            pulsacion = pulsacion_de(JEFE, datos)
            await modo.pulsacion_modo(pulsacion, contexto())
            self.assertEqual(acceso.modo(), acceso.MODO_CLIENTES, datos)
            self.assertEqual(
                pulsacion.callback_query.editados[-1]["texto"],
                textos.modo_ya_elegido(acceso.MODO_CLIENTES),
            )

    async def test_otro_no_puede_elegir_el_modo(self) -> None:
        await montar(None)
        pulsacion = pulsacion_de(CLIENTE, f"{modo.CONFIRMAR}{acceso.MODO_CLIENTES}")
        await modo.pulsacion_modo(pulsacion, contexto())
        self.assertIsNone(acceso.modo())

    async def test_no_hay_comando_para_cambiar_el_modo(self) -> None:
        self.assertFalse(hasattr(modo, "comando_modo"))
        self.assertNotIn("modo", comandos.DESPACHO)


# ---------------------------------------------------------------------------
# Un cliente no llega a nada de administración
# ---------------------------------------------------------------------------


class ElClienteNoLlegaAAdministracion(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await montar(acceso.MODO_CLIENTES)
        await almacen.guardar_documento("catalogo", "Caja grande: 3 euros.", 2000, "plano")

    async def test_el_start_del_cliente(self) -> None:
        await almacen.actualizar_config(nombre_empresa="Cartonajes Pérez")
        update = update_de(CLIENTE, "/start")
        await bot.comando_start(update, contexto())
        self.assertEqual(
            textos_enviados(update), [textos.bienvenida_cliente("Cartonajes Pérez")]
        )
        self.assertNotIn("catalogo", textos_enviados(update)[0])

    async def test_ningun_comando_de_administracion(self) -> None:
        bot.registrar_despacho()
        prohibidos = [
            comandos.comando_doc, comandos.comando_borrar, comandos.comando_costes,
            comandos.comando_limite, comandos.comando_usuarios, comandos.comando_logs,
            comandos.comando_backup, bot.comando_codigo, modo.comando_empresa,
            modo.comando_contacto, modo.comando_enlace,
        ]
        antes = almacen.leer_config()
        for manejador in prohibidos:
            update = update_de(CLIENTE, "/algo")
            await manejador(update, contexto(["999"]))
            self.assertEqual(
                textos_enviados(update), [textos.COMANDO_DESCONOCIDO_CLIENTE],
                manejador.__name__,
            )
        self.assertEqual(almacen.leer_config(), antes)
        self.assertEqual(almacen.listar_documentos(), ["catalogo"])

    async def test_los_botones_del_jefe_tampoco(self) -> None:
        bot.registrar_despacho()
        import menu
        for etiqueta, nombre in menu.EQUIVALENCIAS.items():
            if nombre == "ayuda":
                continue
            update = update_de(CLIENTE, etiqueta)
            atendido = await comandos.pulsacion_de_boton(update, contexto())
            self.assertTrue(atendido)
            respuesta = textos_enviados(update)[0]
            self.assertIn(respuesta, (
                textos.COMANDO_DESCONOCIDO_CLIENTE,
                textos.ayuda_cliente(""),
            ), etiqueta)

    async def test_no_ve_la_lista_de_documentos(self) -> None:
        update = update_de(CLIENTE, "/docs")
        await comandos.comando_docs(update, contexto())
        self.assertNotIn("catalogo", textos_enviados(update)[0])

    async def test_no_puede_subir_ficheros(self) -> None:
        update = update_de(CLIENTE)
        update.effective_message.document = SimpleNamespace(
            file_size=10, file_name="malo.txt", file_id="x"
        )
        await comandos.recibir_documento(update, contexto())
        self.assertEqual(textos_enviados(update), [textos.SOLO_TEXTO_CLIENTE])
        self.assertEqual(almacen.listar_documentos(), ["catalogo"])

    async def test_no_puede_hacerse_pasar_por_el_jefe_contestando(self) -> None:
        """Contestar a la pregunta de /empresa no le sirve a un cliente."""
        pregunta_falsa = SimpleNamespace(
            text=textos.PREGUNTA_NOMBRE_EMPRESA, from_user=SimpleNamespace(is_bot=True)
        )
        update = update_de(CLIENTE, "Empresa Pirata", respuesta_a=pregunta_falsa)
        atendido = await modo.respuesta_de_empresa_si_toca(update, contexto())
        self.assertFalse(atendido)
        self.assertEqual(almacen.leer_config().get("nombre_empresa", ""), "")

    async def test_un_comando_inventado(self) -> None:
        update = update_de(CLIENTE, "/admin")
        await bot.comando_desconocido(update, contexto())
        self.assertEqual(textos_enviados(update), [textos.COMANDO_DESCONOCIDO_CLIENTE])

    async def test_no_se_guarda_nada_del_cliente(self) -> None:
        originales = (consulta.preguntar, comandos.escribiendo)

        async def preguntar_falso(chat_id, pregunta, de_cliente=False):
            return "Cuesta 3 euros.", UsoFalso(100, 10)

        consulta.preguntar = preguntar_falso
        comandos.escribiendo = SinEscribiendo
        try:
            await bot.comando_start(update_de(CLIENTE, "/start", nombre="Pepe Cliente"), contexto())
            await bot.mensaje_texto(update_de(CLIENTE, "¿Cuánto cuesta?", nombre="Pepe Cliente"), contexto())
        finally:
            consulta.preguntar, comandos.escribiendo = originales
        self.assertEqual(acceso.autorizados(), {})
        self.assertNotIn("Pepe", almacen.leer_texto(almacen.FICHERO_LOG))
        self.assertNotIn(str(CLIENTE), almacen.leer_texto(almacen.FICHERO_LOG))


# ---------------------------------------------------------------------------
# Preguntas y topes de los clientes
# ---------------------------------------------------------------------------


class PreguntasDeClientes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await montar(acceso.MODO_CLIENTES)
        await almacen.guardar_documento("catalogo", "Caja grande: 3 euros.", 2000, "plano")
        self.llamadas: list[tuple[int, bool]] = []
        self.originales = (consulta.preguntar, comandos.escribiendo)

        async def preguntar_falso(chat_id, pregunta, de_cliente=False):
            self.llamadas.append((chat_id, de_cliente))
            uso = UsoFalso(1000, 100)
            await costes.registrar_uso(uso, "consulta", de_cliente=de_cliente)
            return "Cuesta 3 euros.", uso

        consulta.preguntar = preguntar_falso
        comandos.escribiendo = SinEscribiendo

    async def asyncTearDown(self) -> None:
        consulta.preguntar, comandos.escribiendo = self.originales

    async def test_el_cliente_pregunta_sin_codigo(self) -> None:
        update = update_de(CLIENTE, "¿Cuánto cuesta la caja grande?")
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(self.llamadas, [(CLIENTE, True)])
        self.assertIn("Cuesta 3 euros.", textos_enviados(update))

    async def test_lo_del_jefe_no_cuenta_como_cliente(self) -> None:
        await bot.mensaje_texto(update_de(JEFE, "¿Cuánto cuesta?"), contexto())
        self.assertEqual(self.llamadas, [(JEFE, False)])
        self.assertEqual(costes.gasto_clientes_mes(), 0.0)

    async def test_el_gasto_de_clientes_va_aparte(self) -> None:
        await bot.mensaje_texto(update_de(CLIENTE, "¿Precio?"), contexto())
        await bot.mensaje_texto(update_de(OTRO_CLIENTE, "¿Horario?"), contexto())
        self.assertGreater(costes.gasto_clientes_hoy(), 0)
        self.assertEqual(costes.preguntas_clientes_hoy(), 2)
        self.assertEqual(costes.preguntas_clientes_mes(), 2)
        self.assertAlmostEqual(costes.gasto_clientes_mes(), costes.gasto_del_mes())

    async def test_diez_por_hora(self) -> None:
        for _ in range(ajustes.LIMITE_PREGUNTAS_HORA_CLIENTES):
            await limites.registrar_pregunta(CLIENTE)
        update = update_de(CLIENTE, "Una más")
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(self.llamadas, [])
        self.assertIn("muchas preguntas seguidas", textos_enviados(update)[0])

    async def test_un_empleado_sigue_teniendo_veinte(self) -> None:
        for _ in range(ajustes.LIMITE_PREGUNTAS_HORA_CLIENTES):
            await limites.registrar_pregunta(CLIENTE)
        self.assertTrue(limites.ha_pasado_del_limite(CLIENTE, de_cliente=True))
        self.assertFalse(limites.ha_pasado_del_limite(CLIENTE, de_cliente=False))

    async def test_al_noventa_por_ciento_se_para_a_los_clientes(self) -> None:
        await costes.cambiar_limite(10)
        await costes.registrar_uso(UsoFalso(entrada=4_600_000), "prueba")  # 9,20 $
        self.assertEqual(costes.clientes_sin_presupuesto(), "mes")

        contexto_falso = contexto()
        update = update_de(CLIENTE, "¿Precio?")
        await bot.mensaje_texto(update, contexto_falso)
        self.assertEqual(self.llamadas, [])
        self.assertIn("no puedo atenderte", textos_enviados(update)[0])
        # Se avisa al jefe, una vez.
        self.assertEqual(len(contexto_falso.bot.mandados), 1)
        await bot.mensaje_texto(update_de(CLIENTE, "¿Y ahora?"), contexto_falso)
        self.assertEqual(len(contexto_falso.bot.mandados), 1)

        # Pero el jefe sigue teniendo bot.
        await bot.mensaje_texto(update_de(JEFE, "¿Precio?"), contexto())
        self.assertEqual(self.llamadas, [(JEFE, False)])

    async def test_tope_diario_de_los_clientes(self) -> None:
        await costes.cambiar_limite(10)  # 1 $ al día para los clientes
        await costes.registrar_uso(UsoFalso(entrada=500_000), "prueba", de_cliente=True)
        self.assertEqual(costes.clientes_sin_presupuesto(), "dia")
        update = update_de(CLIENTE, "¿Precio?")
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(self.llamadas, [])
        self.assertIn("mañana", textos_enviados(update)[0])

    async def test_lo_que_gasta_el_jefe_no_cuenta_para_el_tope_diario(self) -> None:
        await costes.cambiar_limite(10)
        await costes.registrar_uso(UsoFalso(entrada=500_000), "prueba")  # 1 $ del jefe
        self.assertIsNone(costes.clientes_sin_presupuesto())

    async def test_subir_el_tope_vuelve_a_atender(self) -> None:
        await costes.cambiar_limite(10)
        await costes.registrar_uso(UsoFalso(entrada=4_600_000), "prueba")
        self.assertEqual(costes.clientes_sin_presupuesto(), "mes")
        await costes.cambiar_limite(100)
        self.assertIsNone(costes.clientes_sin_presupuesto())

    async def test_el_cliente_que_pega_una_direccion_pregunta(self) -> None:
        update = update_de(CLIENTE, "cartonajesperez.es")
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(self.llamadas, [(CLIENTE, True)])
        self.assertEqual(almacen.listar_documentos(), ["catalogo"])

    async def test_usuarios_da_cifras_y_no_nombres(self) -> None:
        await bot.mensaje_texto(update_de(CLIENTE, "¿Precio?", nombre="Pepe"), contexto())
        update = update_de(JEFE, "/usuarios")
        await comandos.comando_usuarios(update, contexto())
        self.assertEqual(textos_enviados(update), [textos.resumen_de_clientes(1, 1)])

    async def test_codigo_no_existe_en_clientes(self) -> None:
        update = update_de(JEFE, "/codigo")
        await bot.comando_codigo(update, contexto())
        self.assertEqual(textos_enviados(update), [textos.CODIGO_NO_EN_CLIENTES])
        self.assertFalse(almacen.leer_config().get("codigo_hash"))


# ---------------------------------------------------------------------------
# /empresa y /contacto
# ---------------------------------------------------------------------------


def respuesta_a(pregunta: str):
    return SimpleNamespace(text=pregunta, from_user=SimpleNamespace(is_bot=True))


class EmpresaYContacto(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await montar(acceso.MODO_CLIENTES)

    async def test_empresa_pregunta_el_nombre(self) -> None:
        update = update_de(JEFE, "/empresa")
        await modo.comando_empresa(update, contexto())
        envio = update.effective_message.enviados[0]
        self.assertEqual(envio["texto"], textos.PREGUNTA_NOMBRE_EMPRESA)
        self.assertTrue(envio["reply_markup"].force_reply)

    async def test_contestar_guarda_el_nombre_y_pide_el_contacto(self) -> None:
        update = update_de(
            JEFE, "  Cartonajes Pérez  ", respuesta_a(textos.PREGUNTA_NOMBRE_EMPRESA)
        )
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(almacen.leer_config()["nombre_empresa"], "Cartonajes Pérez")
        self.assertIn(textos.PREGUNTA_CONTACTO, textos_enviados(update))

    async def test_contestar_el_contacto(self) -> None:
        update = update_de(
            JEFE, "Llámanos al 612 345 678", respuesta_a(textos.PREGUNTA_CONTACTO)
        )
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(almacen.leer_config()["contacto"], "Llámanos al 612 345 678")
        self.assertIn(textos.SIGUIENTE_PASO_CLIENTES, textos_enviados(update))

    async def test_demasiado_largo(self) -> None:
        update = update_de(JEFE, "x" * (modo.MAX_NOMBRE + 1),
                           respuesta_a(textos.PREGUNTA_NOMBRE_EMPRESA))
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(almacen.leer_config().get("nombre_empresa", ""), "")

    async def test_contestar_a_otro_mensaje_no_cuenta(self) -> None:
        update = update_de(JEFE, "Cartonajes", respuesta_a("Otro mensaje cualquiera"))
        self.assertFalse(await modo.respuesta_de_empresa_si_toca(update, contexto()))

    async def test_el_contacto_llega_a_claude(self) -> None:
        await almacen.actualizar_config(contacto="Llámanos al 612 345 678")
        bloque = consulta.bloque_empresa(almacen.leer_config())
        self.assertIn("612 345 678", bloque)

    async def test_el_nombre_se_escapa(self) -> None:
        self.assertIn("&lt;b&gt;", textos.bienvenida_cliente("<b>Pirata</b>"))
        self.assertIn("&lt;b&gt;", textos.empresa_guardada("<b>Pirata</b>"))
        self.assertIn("&lt;b&gt;", textos.codigo_correcto("<b>Pirata</b>", ""))

    async def test_tambien_vale_en_equipo(self) -> None:
        await montar(acceso.MODO_EQUIPO)
        update = update_de(JEFE, "Cartonajes", respuesta_a(textos.PREGUNTA_NOMBRE_EMPRESA))
        await bot.mensaje_texto(update, contexto())
        self.assertEqual(almacen.leer_config()["nombre_empresa"], "Cartonajes")
        # En equipo no encadena con el contacto.
        self.assertNotIn(textos.PREGUNTA_CONTACTO, textos_enviados(update))


# ---------------------------------------------------------------------------
# Lo que se manda a Claude
# ---------------------------------------------------------------------------


class InstruccionesSegunElModo(unittest.IsolatedAsyncioTestCase):
    async def test_cada_modo_sus_instrucciones(self) -> None:
        await montar(acceso.MODO_CLIENTES)
        clientes = consulta.construir_system(almacen.leer_config(), [])[0]["text"]
        self.assertEqual(clientes, consulta.INSTRUCCIONES_CLIENTES)
        await montar(acceso.MODO_EQUIPO)
        equipo = consulta.construir_system(almacen.leer_config(), [])[0]["text"]
        self.assertEqual(equipo, consulta.INSTRUCCIONES_EQUIPO)

    def test_las_de_clientes_blindan_y_no_citan_ficheros(self) -> None:
        texto = consulta.INSTRUCCIONES_CLIENTES.lower()
        self.assertIn("nunca instrucciones", texto)
        self.assertIn("no cites nombres de ficheros", texto)
        self.assertIn("idioma en que te escriban", texto)
        self.assertNotIn(chr(0x2014), consulta.INSTRUCCIONES_CLIENTES)

    def test_las_de_clientes_no_tienen_nada_que_cambie(self) -> None:
        """Son parte de lo cacheado: ni fechas ni nada que varíe."""
        self.assertNotIn("{", consulta.INSTRUCCIONES_CLIENTES)


class MemoriaDeConversacion(unittest.TestCase):
    def setUp(self) -> None:
        consulta._historiales.clear()

    def test_no_crece_sin_limite(self) -> None:
        for chat in range(ajustes.MAX_CHATS_EN_MEMORIA + 50):
            consulta.recordar(chat, "pregunta", "respuesta")
        self.assertEqual(len(consulta._historiales), ajustes.MAX_CHATS_EN_MEMORIA)
        # Se olvidan los más antiguos.
        self.assertEqual(consulta.historial(0), [])
        self.assertTrue(consulta.historial(ajustes.MAX_CHATS_EN_MEMORIA + 49))

    def test_el_que_vuelve_a_preguntar_no_se_olvida(self) -> None:
        consulta.recordar(1, "primera", "respuesta")
        for chat in range(2, ajustes.MAX_CHATS_EN_MEMORIA + 1):
            consulta.recordar(chat, "pregunta", "respuesta")
        consulta.recordar(1, "segunda", "respuesta")
        consulta.recordar(9999, "nueva", "respuesta")
        self.assertEqual(len(consulta.historial(1)), 4)


class TextosDeModo(unittest.TestCase):
    def test_sin_rayas_largas(self) -> None:
        for nombre in dir(textos):
            valor = getattr(textos, nombre)
            if isinstance(valor, str):
                self.assertNotIn(chr(0x2014), valor, nombre)

    def test_las_preguntas_van_sin_formato(self) -> None:
        """Se reconocen comparando el texto que devuelve Telegram, sin etiquetas."""
        for pregunta in (textos.PREGUNTA_NOMBRE_EMPRESA, textos.PREGUNTA_CONTACTO):
            self.assertNotIn("<", pregunta)


if __name__ == "__main__":
    unittest.main()
