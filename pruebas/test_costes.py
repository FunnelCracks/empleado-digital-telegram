"""Pruebas de costes: tope de gasto, límite por hora y menú de botones.

Sin red. Lo que se verifica aquí es lo que impide una factura sorpresa, que
es el motivo por el que el tope no es opcional.

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

_TEMPORAL = Path(tempfile.mkdtemp(prefix="empleado_pruebas_"))
os.environ["RUTA_DATOS"] = str(_TEMPORAL)
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-prueba")
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-de-prueba")
os.environ["OWNER_CHAT_ID"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ajustes  # noqa: E402
import almacen  # noqa: E402
import consulta  # noqa: E402
import costes  # noqa: E402
import limites  # noqa: E402
import menu  # noqa: E402


def limpiar_volume() -> None:
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)
    almacen.inicializar()


async def gastar(dolares: float) -> None:
    """Deja el contador del mes en la cantidad pedida."""
    datos = costes.datos_del_mes()
    datos["coste_usd"] = dolares
    await almacen.guardar_json(almacen.FICHERO_USO, datos)


# ---------------------------------------------------------------------------
# El tope mensual
# ---------------------------------------------------------------------------


class TopeDeGasto(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_por_defecto_son_veinte(self) -> None:
        self.assertEqual(costes.limite_mensual(), 20.0)

    async def test_el_owner_puede_cambiarlo(self) -> None:
        await costes.cambiar_limite(35)
        self.assertEqual(costes.limite_mensual(), 35.0)

    async def test_el_cambio_sobrevive_a_un_reinicio(self) -> None:
        await costes.cambiar_limite(35)
        # Releer de disco es lo que hace el proceso al arrancar de nuevo.
        self.assertEqual(
            almacen.leer_config().get("limite_mensual_usd"), "35.00"
        )

    async def test_porcentaje(self) -> None:
        await gastar(10.0)
        self.assertAlmostEqual(costes.porcentaje_gastado(), 0.5, places=3)

    async def test_al_llegar_al_tope_corta(self) -> None:
        self.assertFalse(costes.limite_alcanzado())
        await gastar(20.0)
        self.assertTrue(costes.limite_alcanzado())

    async def test_la_consulta_se_niega_si_no_queda_presupuesto(self) -> None:
        await almacen.guardar_documento("tarifas", "90 euros", 3000, "plano")
        await gastar(25.0)
        with self.assertRaises(consulta.LimiteAlcanzado):
            await consulta.preguntar(1, "¿Cuánto cuesta?")

    async def test_subir_el_tope_vuelve_a_dejar_preguntar(self) -> None:
        await gastar(25.0)
        self.assertTrue(costes.limite_alcanzado())
        await costes.cambiar_limite(50)
        self.assertFalse(costes.limite_alcanzado())


class AvisosDeGasto(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_avisa_al_ochenta_por_ciento(self) -> None:
        await gastar(15.0)  # 75%
        self.assertFalse(costes.hay_que_avisar_del_80())
        await gastar(16.5)  # 82,5%
        self.assertTrue(costes.hay_que_avisar_del_80())

    async def test_solo_avisa_una_vez(self) -> None:
        await gastar(16.5)
        self.assertTrue(costes.hay_que_avisar_del_80())
        await costes.marcar_avisado("avisado_80")
        self.assertFalse(costes.hay_que_avisar_del_80())

    async def test_pasado_el_cien_ya_no_toca_el_aviso_del_ochenta(self) -> None:
        await gastar(25.0)
        self.assertFalse(costes.hay_que_avisar_del_80())
        self.assertTrue(costes.hay_que_avisar_del_100())

    async def test_el_aviso_del_cien_tambien_es_una_vez(self) -> None:
        await gastar(25.0)
        await costes.marcar_avisado("avisado_100")
        self.assertFalse(costes.hay_que_avisar_del_100())

    async def test_proyeccion(self) -> None:
        await gastar(5.0)
        self.assertGreaterEqual(costes.proyeccion_fin_de_mes(), 5.0)


# ---------------------------------------------------------------------------
# Límite de preguntas por hora
# ---------------------------------------------------------------------------


class PreguntasPorHora(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_al_principio_no_hay_limite(self) -> None:
        self.assertFalse(limites.ha_pasado_del_limite(555))
        self.assertEqual(limites.quedan(555), ajustes.LIMITE_PREGUNTAS_HORA)

    async def test_corta_al_llegar_al_tope(self) -> None:
        for _ in range(ajustes.LIMITE_PREGUNTAS_HORA):
            await limites.registrar_pregunta(555)
        self.assertTrue(limites.ha_pasado_del_limite(555))
        self.assertEqual(limites.quedan(555), 0)

    async def test_cada_uno_tiene_el_suyo(self) -> None:
        for _ in range(ajustes.LIMITE_PREGUNTAS_HORA):
            await limites.registrar_pregunta(555)
        self.assertTrue(limites.ha_pasado_del_limite(555))
        self.assertFalse(limites.ha_pasado_del_limite(666))

    async def test_sobrevive_a_un_reinicio(self) -> None:
        """Railway reinicia contenedores. En memoria no valdria de nada."""
        for _ in range(ajustes.LIMITE_PREGUNTAS_HORA):
            await limites.registrar_pregunta(555)
        datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        self.assertIn("555", datos["preguntas"])
        self.assertTrue(limites.ha_pasado_del_limite(555))

    async def test_las_viejas_dejan_de_contar(self) -> None:
        antiguo = time.time() - limites.UNA_HORA - 60
        datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        datos["preguntas"] = {"555": [antiguo] * 50}
        await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)
        self.assertEqual(limites.preguntas_en_la_ultima_hora(555), 0)
        self.assertFalse(limites.ha_pasado_del_limite(555))

    async def test_dice_cuanto_hay_que_esperar(self) -> None:
        await limites.registrar_pregunta(555)
        minutos = limites.minutos_hasta_poder_preguntar(555)
        self.assertGreater(minutos, 0)
        self.assertLessEqual(minutos, 61)

    async def test_no_guarda_a_quien_ya_no_cuenta(self) -> None:
        """El fichero no puede crecer sin parar con gente que pasó una vez."""
        antiguo = time.time() - limites.UNA_HORA - 60
        datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        datos["preguntas"] = {"antiguo": [antiguo], "otro": [antiguo]}
        await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)
        await limites.registrar_pregunta(999)
        guardado = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})["preguntas"]
        self.assertEqual(sorted(guardado), ["999"])

    async def test_convive_con_los_bloqueos_por_codigo(self) -> None:
        """Los bloqueos guardan lo suyo en el mismo fichero, sin pisarse."""
        datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        datos["codigos"] = {"777": {"intentos": 3}}
        await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)
        await limites.registrar_pregunta(555)
        guardado = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        self.assertEqual(guardado["codigos"]["777"]["intentos"], 3)
        self.assertIn("555", guardado["preguntas"])


# ---------------------------------------------------------------------------
# El menú de botones
# ---------------------------------------------------------------------------


class MenuDeBotones(unittest.TestCase):
    def test_reconoce_sus_propios_botones(self) -> None:
        self.assertTrue(menu.es_boton(menu.COSTES))
        self.assertEqual(menu.comando_de(menu.COSTES), "costes")

    def test_no_confunde_una_pregunta_con_un_boton(self) -> None:
        self.assertFalse(menu.es_boton("¿Cuánto cuesta la instalación?"))
        self.assertIsNone(menu.comando_de("mis costes"))

    def test_el_owner_ve_mas_botones_que_el_empleado(self) -> None:
        del_owner = menu.teclado_owner().keyboard
        del_empleado = menu.teclado_empleado().keyboard
        self.assertGreater(
            sum(len(fila) for fila in del_owner),
            sum(len(fila) for fila in del_empleado),
        )

    def test_el_empleado_no_ve_nada_de_administracion(self) -> None:
        etiquetas = {
            boton.text for fila in menu.teclado_empleado().keyboard for boton in fila
        }
        for prohibido in (menu.COSTES, menu.BORRAR, menu.CODIGO, menu.SUBIR):
            self.assertNotIn(prohibido, etiquetas)

    def test_ningun_boton_se_queda_sin_handler(self) -> None:
        """Un botón que no hace nada es peor que no tener botón."""
        import bot
        import comandos

        bot.registrar_despacho()
        for etiqueta, nombre in menu.EQUIVALENCIAS.items():
            self.assertIn(nombre, comandos.DESPACHO, f"'{etiqueta}' no hace nada")

    def test_todos_los_botones_estan_en_algun_teclado(self) -> None:
        """Al revés: ninguna equivalencia huérfana que nadie pueda pulsar."""
        en_teclados = {
            boton.text
            for teclado in (menu.teclado_owner(), menu.teclado_empleado())
            for fila in teclado.keyboard
            for boton in fila
        }
        self.assertEqual(set(menu.EQUIVALENCIAS) - en_teclados, set())


class FormatoDeCifras(unittest.TestCase):
    """Las cifras las lee un empresario, no un contable ni un ingles."""

    def test_singular_y_plural_de_centimo(self) -> None:
        import costes as c

        self.assertEqual(c.en_euros(0.0115), "1 céntimo")
        self.assertIn("céntimos", c.en_euros(0.05))

    def test_coma_decimal_y_punto_de_miles(self) -> None:
        import costes as c

        self.assertEqual(c.en_euros(2.0), "1,84 euros")
        self.assertEqual(c.con_miles(30000), "30.000")
        self.assertEqual(c.con_miles(500), "500")

    def test_el_informe_no_se_come_las_comas(self) -> None:
        """Hubo un fallo en que un replace global las convertia en puntos."""
        import textos as t

        informe = t.informe_de_costes(
            gastado="3,13 euros",
            limite_dolares=20.0,
            porcentaje=17,
            preguntas=142,
            coste_pregunta="1 céntimo",
            proyeccion="4,47 euros",
            documentos=2,
            tokens="30.000",
        )
        self.assertIn("3,13 euros", informe)
        self.assertIn("142 preguntas, a unos", informe)
        self.assertNotIn("3.13", informe)

    def test_el_informe_habla_del_tope_en_dolares(self) -> None:
        """Es la unidad en la que el owner lo escribe y la de su saldo."""
        import textos as t

        informe = t.informe_de_costes(
            gastado="3,13 euros", limite_dolares=20.0, porcentaje=17,
            preguntas=0, coste_pregunta="1 céntimo", proyeccion="0",
            documentos=1, tokens="900",
        )
        self.assertIn("20 dólares", informe)
        self.assertNotIn("20.0", informe)
        self.assertIn("todavía no te ha preguntado nadie", informe)


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
