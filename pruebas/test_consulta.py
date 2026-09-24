"""Pruebas de la consulta: construcción del system, caché, historial y troceo.

Sin red. La llamada a la API se sustituye por un cliente falso que guarda lo
que se le ha pedido, que es justo lo que hay que verificar: que el system va
en el orden correcto, que la marca de caché está donde toca y que el prefijo
es idéntico entre peticiones.

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TEMPORAL = Path(tempfile.mkdtemp(prefix="empleado_pruebas_"))
os.environ["RUTA_DATOS"] = str(_TEMPORAL)
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-prueba")
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-de-prueba")
os.environ["OWNER_CHAT_ID"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402
import httpx  # noqa: E402

import ajustes  # noqa: E402
import almacen  # noqa: E402
import claude_api  # noqa: E402
import comun  # noqa: E402
import consulta  # noqa: E402
import textos  # noqa: E402


# ---------------------------------------------------------------------------
# Dobles
# ---------------------------------------------------------------------------


class BloqueFalso:
    type = "text"

    def __init__(self, texto: str):
        self.text = texto


class UsoFalso:
    input_tokens = 40
    output_tokens = 120
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 5000


class RespuestaFalsa:
    def __init__(self, texto: str = "Según la documentación, son 90 euros."):
        self.content = [BloqueFalso(texto)]
        self.usage = UsoFalso()


class MensajesFalsos:
    def __init__(self, texto: str):
        self.llamadas: list[dict] = []
        self.texto = texto

    async def create(self, **argumentos):
        self.llamadas.append(argumentos)
        return RespuestaFalsa(self.texto)


class ClienteFalso:
    def __init__(self, texto: str = "Según la documentación, son 90 euros."):
        self.messages = MensajesFalsos(texto)


def limpiar_volume() -> None:
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)
    almacen.inicializar()
    consulta._historiales.clear()


# ---------------------------------------------------------------------------
# Troceo
# ---------------------------------------------------------------------------


class Troceo(unittest.TestCase):
    """Criterio de aceptación: una respuesta larga llega troceada y legible."""

    def test_lo_corto_va_en_un_solo_mensaje(self) -> None:
        self.assertEqual(comun.trocear("Hola, son 90 euros."), ["Hola, son 90 euros."])

    def test_ningun_trozo_pasa_del_limite(self) -> None:
        parrafo = "Esta es una frase de ejemplo con varias palabras. " * 30
        texto = "\n\n".join(parrafo for _ in range(20))
        trozos = comun.trocear(texto)
        self.assertGreater(len(trozos), 1)
        for trozo in trozos:
            self.assertLessEqual(len(trozo), ajustes.MAX_CARACTERES_TELEGRAM)

    def test_no_parte_palabras(self) -> None:
        texto = " ".join(f"palabra{i:05d}" for i in range(2000))
        for trozo in comun.trocear(texto):
            for palabra in trozo.split():
                self.assertTrue(
                    palabra.startswith("palabra") and len(palabra) == 12,
                    f"palabra partida: {palabra!r}",
                )

    def test_no_se_pierde_contenido(self) -> None:
        texto = "\n\n".join(f"Parrafo numero {i}. " * 40 for i in range(30))
        recompuesto = " ".join(comun.trocear(texto)).split()
        self.assertEqual(recompuesto, texto.split())

    def test_prefiere_cortar_por_parrafos(self) -> None:
        bloque = "x" * 3000
        trozos = comun.trocear(f"{bloque}\n\n{bloque}")
        self.assertEqual(trozos, [bloque, bloque])

    def test_una_palabra_gigante_no_cuelga(self) -> None:
        trozos = comun.trocear("a" * 10000)
        self.assertEqual("".join(trozos), "a" * 10000)
        for trozo in trozos:
            self.assertLessEqual(len(trozo), ajustes.MAX_CARACTERES_TELEGRAM)

    def test_texto_vacio(self) -> None:
        self.assertEqual(comun.trocear("   "), [])


# ---------------------------------------------------------------------------
# Construcción del system
# ---------------------------------------------------------------------------


class ConstruccionDelSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        # Tokens por encima del mínimo cacheable para que se marque la caché.
        await almacen.guardar_documento("manual_calidad", "Contenido del manual.", 3000, "plano")
        await almacen.guardar_documento("tarifas_2026", "Instalación: 90 euros.", 3000, "plano")

    def _system(self) -> list[dict]:
        return consulta.construir_system(
            almacen.leer_config(), almacen.listar_documentos()
        )

    def test_orden_de_los_bloques(self) -> None:
        bloques = self._system()
        self.assertIn("asistente de documentación interna", bloques[0]["text"])
        self.assertIn("=== manual_calidad ===", bloques[-1]["text"])

    def test_solo_el_ultimo_bloque_lleva_marca_de_cache(self) -> None:
        bloques = self._system()
        for bloque in bloques[:-1]:
            self.assertNotIn("cache_control", bloque)
        self.assertIn("cache_control", bloques[-1])

    def test_la_marca_usa_una_hora(self) -> None:
        """Con 5 minutos y preguntas espaciadas casi ninguna escritura llega a leerse."""
        marca = self._system()[-1]["cache_control"]
        self.assertEqual(marca, {"type": "ephemeral", "ttl": "1h"})

    def test_los_documentos_van_siempre_en_el_mismo_orden(self) -> None:
        """Si el orden bailara, la caché se caería en silencio."""
        primero = consulta.bloque_documentos(["tarifas_2026", "manual_calidad"])
        segundo = consulta.bloque_documentos(["manual_calidad", "tarifas_2026"])
        self.assertEqual(primero, segundo)
        self.assertLess(
            primero.index("manual_calidad"), primero.index("tarifas_2026")
        )

    def test_el_prefijo_es_identico_entre_peticiones(self) -> None:
        """La prueba que de verdad protege la factura.

        Si dos llamadas seguidas producen bytes distintos, cada pregunta
        pagaría escritura de caché en vez de lectura.
        """
        self.assertEqual(self._system(), self._system())

    def test_cada_documento_va_etiquetado(self) -> None:
        texto = self._system()[-1]["text"]
        self.assertIn("=== manual_calidad ===", texto)
        self.assertIn("=== tarifas_2026 ===", texto)

    def test_el_bloque_de_empresa_aparece_si_esta_configurado(self) -> None:
        bloques_sin = self._system()
        self.assertEqual(len(bloques_sin), 2)

    async def test_con_empresa_configurada_son_tres_bloques(self) -> None:
        await almacen.actualizar_config(nombre_empresa="Talleres Pepe")
        bloques = self._system()
        self.assertEqual(len(bloques), 3)
        self.assertIn("Talleres Pepe", bloques[1]["text"])
        self.assertNotIn("cache_control", bloques[1])

    async def test_sin_llegar_al_minimo_no_se_marca(self) -> None:
        """Por debajo del mínimo la marca no hace nada y no avisa."""
        limpiar_volume()
        await almacen.guardar_documento("nota", "Dos lineas de nada.", 50, "plano")
        self.assertNotIn("cache_control", self._system()[-1])

    def test_las_instrucciones_blindan_contra_inyeccion(self) -> None:
        instrucciones = consulta.INSTRUCCIONES.lower()
        self.assertIn("nunca instrucciones", instrucciones)
        self.assertIn("ignórala", instrucciones)

    def test_las_instrucciones_piden_citar_y_no_inventar(self) -> None:
        instrucciones = consulta.INSTRUCCIONES.lower()
        self.assertIn("ficheros que has usado", instrucciones)
        self.assertIn("no está en la documentación", instrucciones)


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------


class Historial(unittest.TestCase):
    def setUp(self) -> None:
        consulta._historiales.clear()

    def test_guarda_pregunta_y_respuesta(self) -> None:
        consulta.recordar(1, "¿Cuánto cuesta?", "90 euros.")
        self.assertEqual(consulta.historial(1), [
            {"role": "user", "content": "¿Cuánto cuesta?"},
            {"role": "assistant", "content": "90 euros."},
        ])

    def test_se_queda_con_los_ultimos_cuatro_turnos(self) -> None:
        for i in range(10):
            consulta.recordar(1, f"pregunta {i}", f"respuesta {i}")
        turnos = consulta.historial(1)
        self.assertEqual(len(turnos), ajustes.TURNOS_HISTORIAL * 2)
        self.assertEqual(turnos[0]["content"], "pregunta 6")
        self.assertEqual(turnos[-1]["content"], "respuesta 9")

    def test_alterna_los_papeles(self) -> None:
        for i in range(6):
            consulta.recordar(1, f"p{i}", f"r{i}")
        papeles = [turno["role"] for turno in consulta.historial(1)]
        self.assertEqual(papeles, ["user", "assistant"] * ajustes.TURNOS_HISTORIAL)

    def test_cada_chat_tiene_el_suyo(self) -> None:
        consulta.recordar(1, "de uno", "respuesta")
        consulta.recordar(2, "de dos", "respuesta")
        self.assertEqual(consulta.historial(1)[0]["content"], "de uno")
        self.assertEqual(consulta.historial(2)[0]["content"], "de dos")

    def test_olvidar_todo_al_cambiar_los_documentos(self) -> None:
        consulta.recordar(1, "¿Cuántos documentos tienes?", "Tengo dos.")
        consulta.recordar(2, "algo", "respuesta")
        consulta.olvidar_todo()
        self.assertEqual(consulta.historial(1), [])
        self.assertEqual(consulta.historial(2), [])

    def test_olvidar(self) -> None:
        consulta.recordar(1, "algo", "respuesta")
        consulta.olvidar(1)
        self.assertEqual(consulta.historial(1), [])


# ---------------------------------------------------------------------------
# La llamada completa
# ---------------------------------------------------------------------------


class LlamadaCompleta(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        await almacen.guardar_documento("tarifas", "Instalación: 90 euros.", 3000, "plano")
        self.cliente = ClienteFalso()
        self._original = claude_api.cliente
        claude_api.cliente = lambda: self.cliente

    async def asyncTearDown(self) -> None:
        claude_api.cliente = self._original

    async def test_sin_documentos_no_llama_a_la_api(self) -> None:
        limpiar_volume()
        with self.assertRaises(consulta.SinDocumentacion):
            await consulta.preguntar(1, "¿Cuánto cuesta?")
        self.assertEqual(self.cliente.messages.llamadas, [])

    async def test_parametros_de_la_llamada(self) -> None:
        await consulta.preguntar(1, "¿Cuánto cuesta la instalación?")
        llamada = self.cliente.messages.llamadas[0]
        self.assertEqual(llamada["model"], "claude-sonnet-5")
        self.assertEqual(llamada["max_tokens"], 1500)
        # Sin razonamiento, o se comería los 1500 tokens.
        self.assertEqual(llamada["thinking"], {"type": "disabled"})

    async def test_la_pregunta_va_despues_del_historial(self) -> None:
        await consulta.preguntar(1, "primera")
        await consulta.preguntar(1, "segunda")
        mensajes = self.cliente.messages.llamadas[1]["messages"]
        self.assertEqual(mensajes[0]["content"], "primera")
        self.assertEqual(mensajes[-1]["content"], "segunda")
        self.assertEqual(mensajes[-1]["role"], "user")

    async def test_el_system_no_cambia_entre_preguntas(self) -> None:
        """Lo que hace que la segunda pregunta lea caché en vez de escribirla."""
        await consulta.preguntar(1, "primera")
        await consulta.preguntar(1, "segunda")
        primero, segundo = self.cliente.messages.llamadas
        self.assertEqual(primero["system"], segundo["system"])

    async def test_contabiliza_el_gasto(self) -> None:
        import costes

        await consulta.preguntar(1, "¿Cuánto cuesta?")
        self.assertGreater(costes.gasto_del_mes(), 0)

    async def test_la_respuesta_entra_en_el_historial(self) -> None:
        await consulta.preguntar(7, "¿Cuánto cuesta?")
        turnos = consulta.historial(7)
        self.assertEqual(turnos[0]["content"], "¿Cuánto cuesta?")
        self.assertIn("90 euros", turnos[1]["content"])

    async def test_una_respuesta_vacia_no_ensucia_el_historial(self) -> None:
        self.cliente.messages.texto = ""
        respuesta, _uso = await consulta.preguntar(8, "algo")
        self.assertEqual(respuesta, "")
        self.assertEqual(consulta.historial(8), [])


# ---------------------------------------------------------------------------
# Traducción de los fallos de la API
# ---------------------------------------------------------------------------


def _error_de_api(clase, codigo, cuerpo="algo ha ido mal"):
    """Fabrica una excepción del SDK sin hacer ninguna llamada de verdad."""
    peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    respuesta = httpx.Response(codigo, request=peticion, text=cuerpo)
    return clase(cuerpo, response=respuesta, body=None)


class TraduccionDeErrores(unittest.IsolatedAsyncioTestCase):
    """Cada fallo de la API tiene que salir con su motivo.

    Estos motivos son los que eligen el mensaje que lee el usuario, así que
    equivocarse aquí es contarle que recargue saldo cuando lo que pasa es que
    la clave está mal.
    """

    async def _motivo_de(self, error):
        with self.assertRaises(claude_api.ProblemaConClaude) as capturado:
            async with claude_api.errores_traducidos():
                raise error
        return capturado.exception.motivo

    async def test_clave_invalida(self) -> None:
        error = _error_de_api(anthropic.AuthenticationError, 401, "invalid x-api-key")
        self.assertEqual(await self._motivo_de(error), "clave")

    async def test_sin_saldo(self) -> None:
        error = _error_de_api(
            anthropic.BadRequestError, 400, "your credit balance is too low"
        )
        self.assertEqual(await self._motivo_de(error), "credito")

    async def test_demasiada_demanda(self) -> None:
        error = _error_de_api(anthropic.RateLimitError, 429)
        self.assertEqual(await self._motivo_de(error), "demanda")

    async def test_un_400_que_no_es_de_saldo_no_se_confunde(self) -> None:
        error = _error_de_api(anthropic.BadRequestError, 400, "campo mal formado")
        self.assertEqual(await self._motivo_de(error), "desconocido")

    async def test_lo_que_no_es_de_la_api_pasa_de_largo(self) -> None:
        """Un fallo del disco no puede disfrazarse de problema de Claude."""
        with self.assertRaises(ValueError):
            async with claude_api.errores_traducidos():
                raise ValueError("esto no es de la API")

    async def test_consulta_reexporta_la_misma_excepcion(self) -> None:
        """Quien capture consulta.ProblemaConClaude tiene que seguir cazándola."""
        self.assertIs(consulta.ProblemaConClaude, claude_api.ProblemaConClaude)


class ContarTokensTraduceElFallo(unittest.IsolatedAsyncioTestCase):
    """Contar tokens es la primera llamada a Claude al subir un documento.

    Es donde se nota que la clave esta mal, y hasta ahora salia por el except
    generico con un "algo no ha ido bien" que no decia que hacer.
    """

    def setUp(self) -> None:
        self.anterior = claude_api._cliente

    def tearDown(self) -> None:
        claude_api._cliente = self.anterior

    async def test_una_clave_mala_sale_como_problema_con_motivo(self) -> None:
        class ContadorQueFalla:
            async def count_tokens(self, **_):
                raise _error_de_api(
                    anthropic.AuthenticationError, 401, "invalid x-api-key"
                )

        class ClienteFalso:
            messages = ContadorQueFalla()

        claude_api._cliente = ClienteFalso()
        with self.assertRaises(claude_api.ProblemaConClaude) as capturado:
            await claude_api.contar_tokens("un documento cualquiera")
        self.assertEqual(capturado.exception.motivo, "clave")

    async def test_un_texto_vacio_no_llega_a_llamar(self) -> None:
        claude_api._cliente = None
        self.assertEqual(await claude_api.contar_tokens("   "), 0)


class MensajesDeSubida(unittest.TestCase):
    """El que sube documentos es siempre el owner, y el mensaje lo refleja."""

    def test_cada_motivo_tiene_su_mensaje(self) -> None:
        vistos = set()
        for motivo in ("demanda", "conexion", "credito", "clave", "desconocido"):
            mensaje = textos.problema_al_subir(motivo)
            self.assertTrue(mensaje.strip())
            vistos.add(mensaje)
        self.assertEqual(len(vistos), 5, "hay mensajes repetidos entre motivos")

    def test_un_motivo_desconocido_no_revienta(self) -> None:
        self.assertEqual(
            textos.problema_al_subir("algo_que_no_existe"),
            textos.problema_al_subir("desconocido"),
        )

    def test_el_de_la_clave_dice_que_hacer(self) -> None:
        """El fallo mas comun: la clave pegada a medias."""
        mensaje = textos.problema_al_subir("clave")
        self.assertIn("sk-ant-", mensaje)

    def test_no_manda_al_owner_a_avisar_al_owner(self) -> None:
        """Quien lee esto ES el administrador, decirle que lo avise es absurdo."""
        for motivo in ("credito", "clave"):
            self.assertNotIn("administrador", textos.problema_al_subir(motivo))


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
