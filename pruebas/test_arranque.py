"""Pruebas del arranque: volume vacío, alta de owner y código de acceso.

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# El directorio de datos se fija antes de importar nada del proyecto, porque
# ajustes.py lee el entorno en el momento del import.
_TEMPORAL = Path(tempfile.mkdtemp(prefix="empleado_pruebas_"))
os.environ["RUTA_DATOS"] = str(_TEMPORAL)
os.environ.setdefault("TELEGRAM_TOKEN", "token-de-prueba")
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-de-prueba")
os.environ["OWNER_CHAT_ID"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import acceso  # noqa: E402
import ajustes  # noqa: E402
import almacen  # noqa: E402


def limpiar_volume() -> None:
    """Deja el volume completamente vacio, como un contenedor recien creado."""
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)


class ArranqueConVolumeVacio(unittest.TestCase):
    """Criterio de aceptacion: arranca con el volume vacio y se crea todo solo."""

    def setUp(self) -> None:
        limpiar_volume()

    def test_crea_toda_la_estructura(self) -> None:
        almacen.inicializar()
        self.assertTrue(almacen.DIR_CONOCIMIENTO.is_dir())
        self.assertTrue(almacen.FICHERO_CONFIG.is_file())
        self.assertTrue(almacen.FICHERO_AUTORIZADOS.is_file())
        self.assertTrue(almacen.FICHERO_BLOQUEOS.is_file())
        self.assertTrue(almacen.FICHERO_USO.is_file())
        self.assertTrue(almacen.FICHERO_LOG.is_file())

    def test_es_idempotente(self) -> None:
        almacen.inicializar()
        almacen.FICHERO_CONFIG.write_text("owner_chat_id=12345\n", encoding="utf-8")
        almacen.inicializar()  # segunda llamada, no debe pisar nada
        self.assertEqual(almacen.leer_config().get("owner_chat_id"), "12345")

    def test_tolera_un_json_corrupto(self) -> None:
        almacen.inicializar()
        # Simulamos un reinicio de Railway a mitad de escritura.
        almacen.FICHERO_USO.write_text('{"coste_usd": 3.2', encoding="utf-8")
        datos = almacen.leer_json(almacen.FICHERO_USO, almacen.USO_POR_DEFECTO)
        self.assertEqual(datos["coste_usd"], 0.0)


class EscrituraAtomica(unittest.TestCase):
    def setUp(self) -> None:
        limpiar_volume()
        almacen.inicializar()

    def test_no_deja_temporales(self) -> None:
        ruta = almacen.RUTA_DATOS / "prueba.txt"
        almacen.escribir_atomico(ruta, "contenido")
        self.assertEqual(ruta.read_text(encoding="utf-8"), "contenido")
        self.assertEqual(list(almacen.RUTA_DATOS.glob("*.tmp")), [])

    def test_sobrescribe_entero(self) -> None:
        ruta = almacen.RUTA_DATOS / "prueba.txt"
        almacen.escribir_atomico(ruta, "una linea muy larga de contenido")
        almacen.escribir_atomico(ruta, "corto")
        self.assertEqual(ruta.read_text(encoding="utf-8"), "corto")


class Configuracion(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        almacen.inicializar()

    async def test_ida_y_vuelta(self) -> None:
        await almacen.actualizar_config(nombre_empresa="Talleres Pepe")
        self.assertEqual(almacen.leer_config()["nombre_empresa"], "Talleres Pepe")

    async def test_conserva_saltos_de_linea(self) -> None:
        mensaje = "Hola.\nBienvenido al equipo."
        await almacen.actualizar_config(mensaje_bienvenida=mensaje)
        self.assertEqual(almacen.leer_config()["mensaje_bienvenida"], mensaje)

    async def test_no_pisa_otras_claves(self) -> None:
        await almacen.actualizar_config(nombre_empresa="Talleres Pepe")
        await almacen.actualizar_config(mensaje_bienvenida="Hola")
        config = almacen.leer_config()
        self.assertEqual(config["nombre_empresa"], "Talleres Pepe")
        self.assertEqual(config["mensaje_bienvenida"], "Hola")


class CodigoDeAcceso(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        almacen.inicializar()

    def test_formato_del_codigo(self) -> None:
        codigo = acceso.generar_codigo()
        self.assertEqual(len(codigo), ajustes.LONGITUD_CODIGO)
        self.assertTrue(all(caracter in ajustes.ALFABETO_CODIGO for caracter in codigo))

    def test_sin_caracteres_ambiguos(self) -> None:
        for prohibido in "IlO01":
            self.assertNotIn(prohibido, ajustes.ALFABETO_CODIGO)

    async def test_no_se_guarda_en_claro(self) -> None:
        codigo = await acceso.establecer_codigo_nuevo()
        contenido = almacen.FICHERO_CONFIG.read_text(encoding="utf-8")
        self.assertNotIn(codigo, contenido)
        self.assertIn("codigo_hash=", contenido)

    async def test_acepta_el_codigo_bueno(self) -> None:
        codigo = await acceso.establecer_codigo_nuevo()
        self.assertTrue(acceso.codigo_correcto(codigo))

    async def test_tolera_minusculas_y_espacios(self) -> None:
        codigo = await acceso.establecer_codigo_nuevo()
        self.assertTrue(acceso.codigo_correcto(f"  {codigo.lower()} "))

    async def test_rechaza_el_malo(self) -> None:
        await acceso.establecer_codigo_nuevo()
        self.assertFalse(acceso.codigo_correcto("ZZZZZZ"))
        self.assertFalse(acceso.codigo_correcto(""))

    async def test_el_nuevo_invalida_el_anterior(self) -> None:
        viejo = await acceso.establecer_codigo_nuevo()
        nuevo = await acceso.establecer_codigo_nuevo()
        self.assertNotEqual(viejo, nuevo)
        self.assertFalse(acceso.codigo_correcto(viejo))
        self.assertTrue(acceso.codigo_correcto(nuevo))

    def test_sin_codigo_no_pasa_nadie(self) -> None:
        self.assertFalse(acceso.codigo_correcto("ABCDEF"))


class AltaDeOwner(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        almacen.inicializar()

    async def test_el_primero_se_queda_el_bot(self) -> None:
        self.assertFalse(acceso.hay_owner())
        self.assertTrue(await acceso.registrar_owner(111, "Isaac"))
        self.assertTrue(acceso.es_owner(111))

    async def test_el_segundo_no(self) -> None:
        await acceso.registrar_owner(111, "Isaac")
        self.assertFalse(await acceso.registrar_owner(222, "Intruso"))
        self.assertTrue(acceso.es_owner(111))
        self.assertFalse(acceso.es_owner(222))

    async def test_queda_registrado_en_el_log(self) -> None:
        await acceso.registrar_owner(111, "Isaac")
        self.assertTrue(any("alta_owner" in linea for linea in almacen.ultimos_eventos()))


class Autorizados(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()
        almacen.inicializar()
        await acceso.registrar_owner(111, "Isaac")

    async def test_alta_y_baja(self) -> None:
        self.assertFalse(acceso.esta_autorizado(555))
        await acceso.autorizar(555, "Maria")
        self.assertTrue(acceso.esta_autorizado(555))
        self.assertEqual(acceso.autorizados()[555]["nombre"], "Maria")
        self.assertTrue(await acceso.revocar(555))
        self.assertFalse(acceso.esta_autorizado(555))

    async def test_revocar_a_quien_no_esta(self) -> None:
        self.assertFalse(await acceso.revocar(999))

    async def test_el_owner_siempre_esta_autorizado(self) -> None:
        self.assertTrue(acceso.esta_autorizado(111))

    async def test_sobrevive_a_un_reinicio(self) -> None:
        await acceso.autorizar(555, "Maria")
        # Releer del disco es exactamente lo que hace el proceso al reiniciar.
        self.assertIn(555, acceso.autorizados())


class EstiloDeLosTextos(unittest.TestCase):
    """Guarda las reglas de estilo para que no se pierdan mas adelante."""

    @staticmethod
    def _valor_de_muestra(anotacion):
        """Inventa un valor plausible para poder llamar a la funcion de texto."""
        import typing

        origen = typing.get_origin(anotacion)
        if origen in (list, tuple):
            argumentos = typing.get_args(anotacion)
            if origen is tuple:
                return tuple(
                    EstiloDeLosTextos._valor_de_muestra(a) for a in argumentos if a is not Ellipsis
                )
            interno = argumentos[0] if argumentos else str
            return [EstiloDeLosTextos._valor_de_muestra(interno) for _ in range(2)]
        if anotacion is int:
            return 2
        if anotacion is bool:
            return True
        if anotacion is float:
            return 1.5
        return "muestra"

    def _todos_los_textos(self) -> list[tuple[str, str]]:
        import inspect

        import textos

        encontrados = []
        for nombre, valor in vars(textos).items():
            if nombre.startswith("_"):
                continue
            if isinstance(valor, str):
                encontrados.append((nombre, valor))
            elif inspect.isfunction(valor):
                firma = inspect.signature(valor)
                argumentos = [
                    self._valor_de_muestra(parametro.annotation)
                    for parametro in firma.parameters.values()
                ]
                # Si esto revienta es que la funcion cambio de forma. Que
                # falle la prueba es mejor que revisar un texto de menos.
                encontrados.append((nombre, valor(*argumentos)))
        return encontrados

    def test_no_se_escapa_ningun_texto(self) -> None:
        """La cobertura no puede caerse en silencio al anadir mensajes."""
        import inspect

        import textos

        esperados = {
            nombre
            for nombre, valor in vars(textos).items()
            if not nombre.startswith("_")
            and (isinstance(valor, str) or inspect.isfunction(valor))
        }
        revisados = {nombre for nombre, _ in self._todos_los_textos()}
        self.assertEqual(esperados - revisados, set())

    def test_sin_rayas_largas(self) -> None:
        """Regla de estilo del proyecto: nunca rayas largas como puntuacion."""
        for nombre, texto in self._todos_los_textos():
            for raya in ("—", "–"):
                self.assertNotIn(raya, texto, f"{nombre} contiene una raya larga")

    def test_con_tildes_de_verdad(self) -> None:
        """Se escribe en espanol correcto, no en espanol sin acentuar."""
        import textos

        fuente = Path(textos.__file__).read_text(encoding="utf-8")
        for palabra in ("código", "documentación", "está", "aquí"):
            self.assertIn(palabra, fuente, f"falta la forma acentuada de {palabra}")


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
