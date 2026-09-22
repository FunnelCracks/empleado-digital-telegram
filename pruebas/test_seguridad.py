"""Pruebas de seguridad: bloqueo por códigos fallidos y copia de seguridad.

Sin red.

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

import io
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from datetime import date
from pathlib import Path

_TEMPORAL = Path(tempfile.mkdtemp(prefix="empleado_pruebas_"))
os.environ["RUTA_DATOS"] = str(_TEMPORAL)
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-prueba")
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-de-prueba")
os.environ["OWNER_CHAT_ID"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import acceso  # noqa: E402
import almacen  # noqa: E402
import comun  # noqa: E402
import copia  # noqa: E402
import limites  # noqa: E402


def limpiar_volume() -> None:
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)
    almacen.inicializar()


# ---------------------------------------------------------------------------
# Bloqueo por códigos fallidos
# ---------------------------------------------------------------------------


class BloqueoPorIntentos(unittest.IsolatedAsyncioTestCase):
    """Criterio de aceptación: cinco códigos erróneos bloquean, y el bloqueo
    sobrevive a un reinicio."""

    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_los_cuatro_primeros_fallos_avisan(self) -> None:
        for esperados in (4, 3, 2, 1):
            self.assertEqual(await limites.registrar_fallo(555), esperados)
            self.assertFalse(limites.esta_bloqueado(555))

    async def test_el_quinto_bloquea(self) -> None:
        for _ in range(4):
            await limites.registrar_fallo(555)
        self.assertEqual(await limites.registrar_fallo(555), 0)
        self.assertTrue(limites.esta_bloqueado(555))

    async def test_el_bloqueo_sobrevive_a_un_reinicio(self) -> None:
        """Railway reinicia contenedores. En memoria no valdria de nada."""
        for _ in range(5):
            await limites.registrar_fallo(555)
        # Leer de disco es exactamente lo que hace el proceso al arrancar.
        datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        self.assertGreater(datos["codigos"]["555"]["bloqueado_hasta"], time.time())
        self.assertTrue(limites.esta_bloqueado(555))

    async def test_dura_una_hora(self) -> None:
        for _ in range(5):
            await limites.registrar_fallo(555)
        minutos = limites.minutos_de_bloqueo(555)
        self.assertGreater(minutos, 55)
        self.assertLessEqual(minutos, 61)

    async def test_caduca(self) -> None:
        datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
        datos.setdefault("codigos", {})["555"] = {
            "intentos": 0, "bloqueado_hasta": time.time() - 10,
        }
        await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)
        self.assertFalse(limites.esta_bloqueado(555))
        self.assertEqual(limites.minutos_de_bloqueo(555), 0)

    async def test_acertar_borra_el_contador(self) -> None:
        await limites.registrar_fallo(555)
        await limites.registrar_fallo(555)
        self.assertEqual(limites.intentos_restantes(555), 3)
        await limites.perdonar(555)
        self.assertEqual(limites.intentos_restantes(555), limites.MAX_INTENTOS)

    async def test_bloquea_a_uno_sin_tocar_a_los_demas(self) -> None:
        for _ in range(5):
            await limites.registrar_fallo(555)
        self.assertTrue(limites.esta_bloqueado(555))
        self.assertFalse(limites.esta_bloqueado(666))

    async def test_no_pisa_el_limite_de_preguntas(self) -> None:
        """Las dos cosas viven en bloqueos.json y no se estorban."""
        await limites.registrar_pregunta(555)
        for _ in range(5):
            await limites.registrar_fallo(555)
        self.assertTrue(limites.esta_bloqueado(555))
        self.assertEqual(limites.preguntas_en_la_ultima_hora(555), 1)


# ---------------------------------------------------------------------------
# Copia de seguridad
# ---------------------------------------------------------------------------


class CopiaDeSeguridad(unittest.IsolatedAsyncioTestCase):
    """Criterio de aceptación: /backup devuelve un ZIP restaurable."""

    async def asyncSetUp(self) -> None:
        limpiar_volume()
        await acceso.registrar_owner(111, "Isaac")
        await acceso.establecer_codigo_nuevo()
        await acceso.autorizar(555, "Maria")
        await almacen.guardar_documento("tarifas_2026", "Instalación: 90 euros", 3000, "plano")
        await almacen.guardar_documento("manual", "Procedimiento de calidad", 1500, "plano")

    async def test_es_un_zip_valido(self) -> None:
        nombre, datos = await copia.construir()
        self.assertTrue(nombre.endswith(".zip"))
        self.assertIn(date.today().isoformat(), nombre)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(datos)))

    async def test_lleva_todo_lo_que_hace_falta(self) -> None:
        _nombre, datos = await copia.construir()
        with zipfile.ZipFile(io.BytesIO(datos)) as zip_:
            dentro = set(zip_.namelist())
        for imprescindible in (
            "config.txt", "autorizados.txt", "documentos.json",
            "knowledge/tarifas_2026.txt", "knowledge/manual.txt", "LEEME.txt",
        ):
            self.assertIn(imprescindible, dentro)

    async def test_los_documentos_se_pueden_leer_del_zip(self) -> None:
        _nombre, datos = await copia.construir()
        with zipfile.ZipFile(io.BytesIO(datos)) as zip_:
            contenido = zip_.read("knowledge/tarifas_2026.txt").decode("utf-8")
        self.assertIn("Instalación: 90 euros", contenido)

    async def test_no_lleva_los_bloqueos(self) -> None:
        """Son temporales. Restaurarlos solo reviviria bloqueos caducados."""
        _nombre, datos = await copia.construir()
        with zipfile.ZipFile(io.BytesIO(datos)) as zip_:
            self.assertNotIn("bloqueos.json", zip_.namelist())

    async def test_el_leeme_explica_como_recuperarse(self) -> None:
        _nombre, datos = await copia.construir()
        with zipfile.ZipFile(io.BytesIO(datos)) as zip_:
            leeme = zip_.read("LEEME.txt").decode("utf-8")
        self.assertIn("volver a subir", leeme)
        self.assertIn("/codigo", leeme)


class CuandoTocaLaCopiaAutomatica(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_sin_documentos_no_toca(self) -> None:
        self.assertFalse(copia.toca_copia_automatica())

    async def test_con_documentos_y_sin_copia_previa_si_toca(self) -> None:
        await almacen.guardar_documento("tarifas", "x", 100, "plano")
        self.assertTrue(copia.toca_copia_automatica())

    async def test_solo_una_al_dia(self) -> None:
        await almacen.guardar_documento("tarifas", "x", 100, "plano")
        await copia.marcar_copia_hecha()
        self.assertFalse(copia.toca_copia_automatica())

    async def test_al_dia_siguiente_vuelve_a_tocar(self) -> None:
        await almacen.guardar_documento("tarifas", "x", 100, "plano")
        await almacen.actualizar_config(ultima_copia="2001-01-01")
        self.assertTrue(copia.toca_copia_automatica())


# ---------------------------------------------------------------------------
# Registro de accesos
# ---------------------------------------------------------------------------


class RegistroLegible(unittest.TestCase):
    def test_traduce_el_evento(self) -> None:
        linea = comun.formatear_evento(
            "2026-09-21T18:08:00+00:00\tacceso_concedido\t555\tMaria Lopez"
        )
        self.assertIn("Maria Lopez", linea)
        self.assertIn("entró con el código", linea)
        self.assertNotIn("acceso_concedido", linea)

    def test_pone_la_hora_de_espana(self) -> None:
        """En septiembre Madrid va dos horas por delante de UTC."""
        linea = comun.formatear_evento(
            "2026-09-21T18:08:00+00:00\tcodigo_fallido\t666\tAlguien"
        )
        self.assertIn("21/09 a las 20:08", linea)

    def test_aguanta_una_linea_rara(self) -> None:
        """Un log a medias por un reinicio no puede tirar el comando."""
        for basura in ("", "solo_una_cosa", "a\tb", "\t\t\t"):
            comun.formatear_evento(basura)

    def test_un_evento_que_no_conoce_no_rompe(self) -> None:
        linea = comun.formatear_evento("2026-09-21T18:08:00+00:00\tevento_raro\t1\tPepe")
        self.assertIn("evento raro", linea)


# ---------------------------------------------------------------------------
# Revocar acceso
# ---------------------------------------------------------------------------


class RevocarAcceso(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        await acceso.registrar_owner(111, "Isaac")
        await acceso.autorizar(555, "Maria")
        await acceso.autorizar(666, "Pedro")

    async def test_quita_a_uno_y_deja_al_otro(self) -> None:
        self.assertTrue(await acceso.revocar(555))
        self.assertFalse(acceso.esta_autorizado(555))
        self.assertTrue(acceso.esta_autorizado(666))

    async def test_queda_registrado(self) -> None:
        await acceso.revocar(555)
        self.assertTrue(
            any("acceso_revocado" in linea for linea in almacen.ultimos_eventos())
        )

    async def test_al_owner_no_se_le_puede_quitar_por_aqui(self) -> None:
        """El owner no esta en autorizados.txt, asi que no aparece en la lista."""
        self.assertNotIn(111, acceso.autorizados())
        self.assertTrue(acceso.esta_autorizado(111))


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
