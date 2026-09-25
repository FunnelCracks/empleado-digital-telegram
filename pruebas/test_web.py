"""Pruebas de la lectura de páginas web.

No salen a internet: las descargas pasan por un transporte falso de httpx y
las llamadas a Claude se sustituyen por dobles.

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

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

import httpx  # noqa: E402

import acceso  # noqa: E402
import almacen  # noqa: E402
import claude_api  # noqa: E402
import comandos  # noqa: E402
import textos  # noqa: E402
import web  # noqa: E402

OWNER = 1111
EMPLEADO = 2222

PARRAFO = (
    "Fabricamos cajas de cartón a medida para empresas de alimentación. "
    "El pedido mínimo son 500 unidades y el plazo de entrega es de diez días "
    "laborables. Los portes son gratis a partir de 300 euros. "
)

PAGINA_NORMAL = f"""<!doctype html>
<html><head><title>Cartonajes Pérez | Servicios</title></head>
<body>
<nav><a href="/">Inicio</a> <a href="/contacto">Contacto</a></nav>
<main><article>
<h1>Nuestros servicios</h1>
<p>{PARRAFO}</p>
<p>{PARRAFO}</p>
</article></main>
<footer>Aviso legal. Política de cookies.</footer>
</body></html>"""

PAGINA_DE_BLOQUEO = """<!doctype html><html><head><title>Just a moment...</title></head>
<body><div id="cf-challenge">Checking your browser.</div></body></html>"""

PAGINA_VACIA = """<!doctype html><html><head><title>Mi tienda</title></head>
<body><div id="root"></div><script src="/app.js"></script></body></html>"""


def transporte(rutas: dict[str, httpx.Response]) -> httpx.MockTransport:
    def responder(peticion: httpx.Request) -> httpx.Response:
        return rutas.get(str(peticion.url), httpx.Response(404))
    return httpx.MockTransport(responder)


def html(contenido: str, codigo: int = 200) -> httpx.Response:
    return httpx.Response(
        codigo, headers={"content-type": "text/html; charset=utf-8"},
        content=contenido.encode("utf-8"),
    )


def limpiar_volume() -> None:
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)
    almacen.inicializar()


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


# ---------------------------------------------------------------------------
# Reconocer direcciones
# ---------------------------------------------------------------------------


class ReconocerDirecciones(unittest.TestCase):
    def test_una_direccion_sin_https(self) -> None:
        self.assertEqual(
            web.direcciones_del_mensaje("iaparaempresarios.es"),
            ["https://iaparaempresarios.es"],
        )

    def test_varias_una_por_linea(self) -> None:
        texto = "https://miweb.es/servicios\nwww.miweb.es/precios\n\nmiweb.es/faq"
        self.assertEqual(web.direcciones_del_mensaje(texto), [
            "https://miweb.es/servicios",
            "https://www.miweb.es/precios",
            "https://miweb.es/faq",
        ])

    def test_una_pregunta_con_una_direccion_sigue_siendo_pregunta(self) -> None:
        self.assertEqual(
            web.direcciones_del_mensaje("¿Qué pone en miweb.es sobre los envíos?"), []
        )

    def test_texto_normal_no_es_direccion(self) -> None:
        self.assertEqual(web.direcciones_del_mensaje("hola"), [])
        self.assertEqual(web.direcciones_del_mensaje("¿Cuánto cuesta la caja 3?"), [])
        self.assertEqual(web.direcciones_del_mensaje(""), [])

    def test_no_repite(self) -> None:
        self.assertEqual(
            web.direcciones_del_mensaje("miweb.es https://miweb.es"),
            ["https://miweb.es"],
        )

    def test_quita_el_punto_final(self) -> None:
        self.assertEqual(web.normalizar("miweb.es/precios."), "https://miweb.es/precios")


class NombreDelDocumento(unittest.TestCase):
    def test_portada(self) -> None:
        self.assertEqual(web.nombre_para("https://www.miweb.es/"), "web_miweb")

    def test_con_ruta(self) -> None:
        self.assertEqual(
            web.nombre_para("https://miweb.es/servicios/cajas-a-medida"),
            "web_miweb_servicios_cajas_a_medida",
        )

    def test_la_misma_direccion_da_el_mismo_nombre(self) -> None:
        """Así volver a pegarla actualiza el documento en vez de duplicarlo."""
        self.assertEqual(
            web.nombre_para("https://www.miweb.es/precios"),
            web.nombre_para("https://miweb.es/precios/"),
        )

    def test_cabe_en_el_boton_de_quitar(self) -> None:
        """Telegram no admite más de 64 bytes en los datos de un botón."""
        nombre = web.nombre_para("https://miweb.es/" + "muy-largo/" * 20)
        self.assertLessEqual(len(f"{comandos.PREFIJO_BORRAR}{nombre}".encode()), 64)


# ---------------------------------------------------------------------------
# Que no mire dentro de la red del servidor
# ---------------------------------------------------------------------------


class RedInterna(unittest.IsolatedAsyncioTestCase):
    def test_direcciones_internas(self) -> None:
        for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1",
                   "169.254.169.254", "::1", "fd00::1", "0.0.0.0"):
            self.assertTrue(web.es_direccion_interna(ip), ip)

    def test_direcciones_publicas(self) -> None:
        for ip in ("8.8.8.8", "1.1.1.1", "2a00:1450:4003:80e::200e"):
            self.assertFalse(web.es_direccion_interna(ip), ip)

    async def test_localhost_se_rechaza(self) -> None:
        with self.assertRaises(web.WebNoLeida) as error:
            await web.comprobar_destino("http://localhost:8080/")
        self.assertEqual(error.exception.motivo, "interna")

    async def test_una_ip_interna_se_rechaza(self) -> None:
        with self.assertRaises(web.WebNoLeida) as error:
            await web.comprobar_destino("http://10.0.0.5/admin")
        self.assertEqual(error.exception.motivo, "interna")

    async def test_otro_protocolo_se_rechaza(self) -> None:
        with self.assertRaises(web.WebNoLeida):
            await web.comprobar_destino("file:///etc/passwd")


# ---------------------------------------------------------------------------
# Leer la página
# ---------------------------------------------------------------------------


class LeerPagina(unittest.IsolatedAsyncioTestCase):
    async def test_saca_el_contenido_y_el_titulo(self) -> None:
        falso = transporte({"https://miweb.es/servicios": html(PAGINA_NORMAL)})
        pagina = await web.leer_pagina("https://miweb.es/servicios", falso)
        self.assertEqual(pagina.titulo, "Cartonajes Pérez | Servicios")
        self.assertIn("pedido mínimo son 500 unidades", pagina.documento.texto)
        self.assertEqual(pagina.documento.origen, "web")

    async def test_el_texto_dice_de_donde_viene(self) -> None:
        falso = transporte({"https://miweb.es/servicios": html(PAGINA_NORMAL)})
        pagina = await web.leer_pagina("https://miweb.es/servicios", falso)
        self.assertTrue(pagina.documento.texto.startswith(
            "Página web: https://miweb.es/servicios"
        ))

    async def test_quita_menus_y_pie(self) -> None:
        falso = transporte({"https://miweb.es/servicios": html(PAGINA_NORMAL)})
        pagina = await web.leer_pagina("https://miweb.es/servicios", falso)
        self.assertNotIn("Política de cookies", pagina.documento.texto)

    async def test_sigue_las_redirecciones(self) -> None:
        falso = transporte({
            "https://miweb.es/": httpx.Response(301, headers={"location": "/inicio"}),
            "https://miweb.es/inicio": html(PAGINA_NORMAL),
        })
        pagina = await web.leer_pagina("https://miweb.es/", falso)
        self.assertEqual(pagina.direccion, "https://miweb.es/inicio")

    async def test_no_se_queda_en_un_bucle_de_redirecciones(self) -> None:
        falso = transporte({
            "https://miweb.es/a": httpx.Response(302, headers={"location": "/b"}),
            "https://miweb.es/b": httpx.Response(302, headers={"location": "/a"}),
        })
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/a", falso)
        self.assertEqual(error.exception.motivo, "no_responde")

    async def test_bloqueo_por_codigo(self) -> None:
        falso = transporte({"https://miweb.es/": html(PAGINA_DE_BLOQUEO, 403)})
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/", falso)
        self.assertEqual(error.exception.motivo, "bloqueada")

    async def test_bloqueo_que_llega_como_si_todo_fuera_bien(self) -> None:
        falso = transporte({"https://miweb.es/": html(PAGINA_DE_BLOQUEO, 200)})
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/", falso)
        self.assertEqual(error.exception.motivo, "bloqueada")

    async def test_web_que_se_monta_con_javascript(self) -> None:
        falso = transporte({"https://mitienda.es/": html(PAGINA_VACIA)})
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://mitienda.es/", falso)
        self.assertEqual(error.exception.motivo, "sin_texto")

    async def test_pagina_privada(self) -> None:
        falso = transporte({"https://miweb.es/intranet": html("", 401)})
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/intranet", falso)
        self.assertEqual(error.exception.motivo, "privada")

    async def test_pagina_que_no_existe(self) -> None:
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/nada", transporte({}))
        self.assertEqual(error.exception.motivo, "no_existe")

    async def test_una_imagen_no_es_una_pagina(self) -> None:
        falso = transporte({"https://miweb.es/logo.png": httpx.Response(
            200, headers={"content-type": "image/png"}, content=b"\x89PNG"
        )})
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/logo.png", falso)
        self.assertEqual(error.exception.motivo, "formato")

    async def test_pagina_enorme(self) -> None:
        falso = transporte({"https://miweb.es/": httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"a" * (web.MAX_BYTES_PAGINA + 1),
        )})
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/", falso)
        self.assertEqual(error.exception.motivo, "demasiado_grande")

    async def test_la_web_no_contesta(self) -> None:
        def sin_respuesta(peticion: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("tarda demasiado", request=peticion)
        with self.assertRaises(web.WebNoLeida) as error:
            await web.leer_pagina("https://miweb.es/", httpx.MockTransport(sin_respuesta))
        self.assertEqual(error.exception.motivo, "no_responde")


# ---------------------------------------------------------------------------
# El resumen
# ---------------------------------------------------------------------------


class InterpretarResumen(unittest.TestCase):
    def test_valida(self) -> None:
        valida, resumen = claude_api.interpretar_resumen("VALIDA\nFabrican cajas.")
        self.assertTrue(valida)
        self.assertEqual(resumen, "Fabrican cajas.")

    def test_basura(self) -> None:
        valida, resumen = claude_api.interpretar_resumen("BASURA\nEs un aviso de cookies.")
        self.assertFalse(valida)
        self.assertEqual(resumen, "Es un aviso de cookies.")

    def test_con_tilde_o_adornos(self) -> None:
        self.assertTrue(claude_api.interpretar_resumen("**Válida.**\nAlgo.")[0])

    def test_si_no_sigue_el_formato_se_da_por_buena(self) -> None:
        valida, resumen = claude_api.interpretar_resumen("Fabrican cajas de cartón.")
        self.assertTrue(valida)
        self.assertEqual(resumen, "Fabrican cajas de cartón.")


class TextosDeWeb(unittest.TestCase):
    def test_lo_que_viene_de_fuera_se_escapa(self) -> None:
        """Un < suelto en un título haría que Telegram rechazara el mensaje."""
        mensaje = textos.web_guardada(
            nombre="web_x", direccion="https://x.es/?a=1&b=2", titulo="<Ofertas>",
            resumen="Precios < 10 €", tokens=1200, total_documentos=2,
            coste_caliente="1 céntimo", sobrescrito=False,
        )
        self.assertIn("&lt;Ofertas&gt;", mensaje)
        self.assertIn("Precios &lt; 10 €", mensaje)
        self.assertIn("a=1&amp;b=2", mensaje)

    def test_siempre_ofrece_el_pdf(self) -> None:
        for motivo in ("privada", "bloqueada", "no_existe", "no_responde",
                       "sin_texto", "formato", "demasiado_grande", "desconocido"):
            self.assertIn("Guardar como PDF", textos.web_no_leida("https://x.es", motivo))

    def test_sin_rayas_largas(self) -> None:
        for texto in (textos.COMO_GUARDAR_EN_PDF, textos.SOLO_OWNER_WEBS,
                      *textos._POR_QUE_NO_SE_LEE.values()):
            self.assertNotIn(chr(0x2014), texto)


# ---------------------------------------------------------------------------
# El recorrido completo, con Telegram y Claude de mentira
# ---------------------------------------------------------------------------


class MensajeFalso:
    def __init__(self) -> None:
        self.enviados: list[dict] = []

    async def reply_text(self, texto: str, **opciones) -> None:
        self.enviados.append({"texto": texto, **opciones})


def update_de(chat_id: int) -> SimpleNamespace:
    mensaje = MensajeFalso()
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_message=mensaje,
        effective_user=None,
    )


class RecorridoCompleto(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        await acceso.registrar_owner(OWNER, "Jefa")
        self.originales = (
            web.leer_pagina, claude_api.resumir_web, claude_api.contar_tokens,
            comandos.escribiendo, comandos.copia_automatica_si_toca,
        )
        self.veredicto = (True, "Fabrican cajas de cartón a medida.")

        async def leer_falso(direccion: str):
            return web.PaginaLeida(direccion, "Servicios", web.extraccion.Documento(
                texto=f"Página web: {direccion}\n\n{PARRAFO}", origen="web"
            ))

        async def resumir_falso(texto: str):
            return (*self.veredicto, SimpleNamespace(input_tokens=10, output_tokens=5))

        async def contar_falso(texto: str) -> int:
            return 1200

        class EscribiendoFalso:
            def __init__(self, update) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *error) -> None:
                return None

        async def sin_copia(context) -> None:
            return None

        web.leer_pagina = leer_falso
        claude_api.resumir_web = resumir_falso
        claude_api.contar_tokens = contar_falso
        comandos.escribiendo = EscribiendoFalso
        comandos.copia_automatica_si_toca = sin_copia

    async def asyncTearDown(self) -> None:
        (web.leer_pagina, claude_api.resumir_web, claude_api.contar_tokens,
         comandos.escribiendo, comandos.copia_automatica_si_toca) = self.originales

    async def test_el_owner_pega_una_direccion_y_se_guarda(self) -> None:
        update = update_de(OWNER)
        atendido = await comandos.recibir_webs_si_toca(update, None, "miweb.es/servicios")
        self.assertTrue(atendido)
        self.assertIn("web_miweb_servicios", almacen.listar_documentos())
        ultimo = update.effective_message.enviados[-1]
        self.assertIn("Fabrican cajas", ultimo["texto"])
        boton = ultimo["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(boton.callback_data, "borrar:web_miweb_servicios")

    async def test_si_es_basura_no_se_guarda(self) -> None:
        self.veredicto = (False, "Es un aviso de cookies.")
        update = update_de(OWNER)
        await comandos.recibir_webs_si_toca(update, None, "miweb.es")
        self.assertEqual(almacen.listar_documentos(), [])
        self.assertIn("Guardar como PDF", update.effective_message.enviados[-1]["texto"])

    async def test_un_empleado_no_puede_anadir_webs(self) -> None:
        update = update_de(EMPLEADO)
        atendido = await comandos.recibir_webs_si_toca(update, None, "miweb.es")
        self.assertTrue(atendido)
        self.assertEqual(almacen.listar_documentos(), [])
        self.assertEqual(update.effective_message.enviados[-1]["texto"], textos.SOLO_OWNER_WEBS)

    async def test_una_pregunta_no_la_toca(self) -> None:
        update = update_de(OWNER)
        atendido = await comandos.recibir_webs_si_toca(update, None, "¿Cuánto cuesta el envío?")
        self.assertFalse(atendido)
        self.assertEqual(update.effective_message.enviados, [])

    async def test_si_una_falla_sigue_con_las_demas(self) -> None:
        leer_bueno = web.leer_pagina

        async def leer_a_medias(direccion: str):
            if "rota" in direccion:
                raise web.WebNoLeida("bloqueada")
            return await leer_bueno(direccion)

        web.leer_pagina = leer_a_medias
        update = update_de(OWNER)
        await comandos.recibir_webs_si_toca(update, None, "miweb.es/rota\nmiweb.es/buena")
        self.assertEqual(almacen.listar_documentos(), ["web_miweb_buena"])

    async def test_demasiadas_de_golpe(self) -> None:
        update = update_de(OWNER)
        texto = "\n".join(f"miweb.es/p{i}" for i in range(web.MAX_DIRECCIONES + 1))
        await comandos.recibir_webs_si_toca(update, None, texto)
        self.assertEqual(almacen.listar_documentos(), [])


if __name__ == "__main__":
    unittest.main()
