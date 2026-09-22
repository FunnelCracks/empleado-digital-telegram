"""Pruebas de documentos: extracción y contabilidad de tokens.

No tocan la red. Las llamadas a Claude se sustituyen por dobles en los dos
casos que las necesitan (PDF escaneado y foto).

Se ejecutan con:  python -m unittest discover -s pruebas -v
"""

import asyncio
import io
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

import ajustes  # noqa: E402
import almacen  # noqa: E402
import claude_api  # noqa: E402
import costes  # noqa: E402
import extraccion  # noqa: E402


# ---------------------------------------------------------------------------
# Generadores de ficheros de prueba
# ---------------------------------------------------------------------------


def pdf_con_texto(paginas: list[str]) -> bytes:
    """Construye un PDF valido con texto real, sin dependencias extra.

    Se hace a mano en vez de con reportlab para no anadir una libreria al
    proyecto solo para las pruebas.
    """
    def escapar(texto: str) -> str:
        return texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    total = len(paginas)
    id_pagina = {indice: 4 + indice * 2 for indice in range(total)}
    id_contenido = {indice: 5 + indice * 2 for indice in range(total)}

    objetos: dict[int, bytes] = {}
    objetos[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    hijos = " ".join(f"{id_pagina[i]} 0 R" for i in range(total))
    objetos[2] = f"<< /Type /Pages /Kids [{hijos}] /Count {total} >>".encode()
    objetos[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for indice, texto in enumerate(paginas):
        objetos[id_pagina[indice]] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {id_contenido[indice]} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>"
        ).encode()
        flujo = f"BT /F1 12 Tf 50 750 Td ({escapar(texto)}) Tj ET".encode()
        objetos[id_contenido[indice]] = (
            f"<< /Length {len(flujo)} >>\nstream\n".encode() + flujo + b"\nendstream"
        )

    salida = bytearray(b"%PDF-1.4\n")
    posiciones: dict[int, int] = {}
    for numero in sorted(objetos):
        posiciones[numero] = len(salida)
        salida += f"{numero} 0 obj\n".encode() + objetos[numero] + b"\nendobj\n"

    inicio_xref = len(salida)
    maximo = max(objetos) + 1
    salida += f"xref\n0 {maximo}\n".encode()
    salida += b"0000000000 65535 f \n"
    for numero in range(1, maximo):
        if numero in posiciones:
            salida += f"{posiciones[numero]:010d} 00000 n \n".encode()
        else:
            salida += b"0000000000 65535 f \n"
    salida += (
        f"trailer\n<< /Size {maximo} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(salida)


def pdf_sin_texto(paginas: int = 2) -> bytes:
    """Un PDF con paginas vacias, que es lo que parece un escaneado a pypdf."""
    return pdf_con_texto([""] * paginas)


def docx_con_texto(parrafos: list[str], tabla: list[list[str]] | None = None) -> bytes:
    from docx import Document

    documento = Document()
    for parrafo in parrafos:
        documento.add_paragraph(parrafo)
    if tabla:
        objeto = documento.add_table(rows=len(tabla), cols=len(tabla[0]))
        for fila_indice, fila in enumerate(tabla):
            for columna_indice, valor in enumerate(fila):
                objeto.cell(fila_indice, columna_indice).text = valor
    memoria = io.BytesIO()
    documento.save(memoria)
    return memoria.getvalue()


def limpiar_volume() -> None:
    if almacen.RUTA_DATOS.exists():
        shutil.rmtree(almacen.RUTA_DATOS)
    almacen.RUTA_DATOS.mkdir(parents=True)
    almacen.inicializar()


# ---------------------------------------------------------------------------
# Nombres de fichero
# ---------------------------------------------------------------------------


class SaneadoDeNombres(unittest.TestCase):
    def test_quita_tildes_y_enes(self) -> None:
        self.assertEqual(extraccion.sanear_nombre("Tarifas Año 2026.pdf"), "tarifas_ano_2026")

    def test_quita_espacios_y_mayusculas(self) -> None:
        self.assertEqual(extraccion.sanear_nombre("Manual  DE Calidad.docx"), "manual_de_calidad")

    def test_bloquea_rutas(self) -> None:
        """Nadie puede escribir fuera de knowledge/ poniendo barras en el nombre."""
        for peligroso in ("../../config.txt", "..\\..\\config.txt", "/etc/passwd"):
            saneado = extraccion.sanear_nombre(peligroso)
            self.assertNotIn("/", saneado)
            self.assertNotIn("\\", saneado)
            self.assertNotIn("..", saneado)

    def test_nunca_devuelve_vacio(self) -> None:
        for raro in ("", "...", "???", "   "):
            self.assertTrue(extraccion.sanear_nombre(raro))

    def test_cabe_en_un_boton_de_telegram(self) -> None:
        """El callback_data de /borrar tiene un tope de 64 bytes."""
        largo = extraccion.sanear_nombre("a" * 300 + ".pdf")
        self.assertLessEqual(len(f"borrar:{largo}".encode()), 64)


# ---------------------------------------------------------------------------
# Texto plano y CSV
# ---------------------------------------------------------------------------


class TextoPlano(unittest.TestCase):
    def test_utf8(self) -> None:
        documento = extraccion.extraer_plano("Tarifa de instalación: 90 €".encode("utf-8"), "t.txt")
        self.assertIn("instalación", documento.texto)
        self.assertIn("€", documento.texto)

    def test_excel_en_espanol(self) -> None:
        """Excel guarda los CSV en cp1252 y hay que aguantarlo sin romperse."""
        documento = extraccion.extraer_plano("Camión; Grúa".encode("cp1252"), "t.txt")
        self.assertIn("Camión", documento.texto)

    def test_csv_con_punto_y_coma(self) -> None:
        crudo = "producto;precio\nTornillo;0,15\nTuerca;0,10\n".encode("utf-8")
        documento = extraccion.extraer_plano(crudo, "tarifas.csv")
        self.assertIn("producto\tprecio", documento.texto)
        self.assertIn("Tornillo\t0,15", documento.texto)

    def test_vacio_da_error_entendible(self) -> None:
        with self.assertRaises(extraccion.ErrorExtraccion):
            extraccion.extraer_plano(b"   \n  ", "vacio.txt")


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------


class Word(unittest.IsolatedAsyncioTestCase):
    async def test_parrafos_y_tablas(self) -> None:
        datos = docx_con_texto(
            ["Condiciones de entrega", "Plazo de 48 horas"],
            tabla=[["Zona", "Precio"], ["Peninsula", "5 euros"]],
        )
        documento = await extraccion.extraer_docx(datos)
        self.assertIn("Condiciones de entrega", documento.texto)
        self.assertIn("Zona\tPrecio", documento.texto)
        self.assertIn("Peninsula\t5 euros", documento.texto)
        self.assertEqual(documento.origen, "docx")

    async def test_word_vacio(self) -> None:
        with self.assertRaises(extraccion.ErrorExtraccion):
            await extraccion.extraer_docx(docx_con_texto([]))

    async def test_fichero_que_no_es_word(self) -> None:
        with self.assertRaises(extraccion.ErrorExtraccion):
            await extraccion.extraer_docx(b"esto no es un docx")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


class PdfDigital(unittest.IsolatedAsyncioTestCase):
    """Criterio de aceptacion: un PDF digital se procesa sin llamar a Claude."""

    async def test_no_llama_a_claude(self) -> None:
        llamadas = []

        async def espia(datos):
            llamadas.append(datos)
            return "no deberia llamarse", None

        original = claude_api.leer_pdf_escaneado
        claude_api.leer_pdf_escaneado = espia
        try:
            paginas = [f"Pagina {i} con texto de sobra " * 8 for i in range(1, 51)]
            documento = await extraccion.extraer_pdf(pdf_con_texto(paginas))
        finally:
            claude_api.leer_pdf_escaneado = original

        self.assertEqual(llamadas, [], "no debia llamar a Claude en un PDF digital")
        self.assertEqual(documento.origen, "pypdf")
        self.assertEqual(documento.paginas, 50)
        self.assertIn("Pagina 1", documento.texto)
        self.assertIn("Pagina 50", documento.texto)

    async def test_pdf_corrupto(self) -> None:
        with self.assertRaises(extraccion.ErrorExtraccion):
            await extraccion.extraer_pdf(b"%PDF-1.4 esto esta roto")


class PdfEscaneado(unittest.IsolatedAsyncioTestCase):
    """Criterio de aceptacion: un PDF escaneado se procesa via Claude."""

    async def test_cae_en_claude(self) -> None:
        llamadas = []

        class UsoFalso:
            input_tokens = 1200
            output_tokens = 300
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0

        async def doble(datos):
            llamadas.append(datos)
            return "Texto sacado del escaneo", UsoFalso()

        original = claude_api.leer_pdf_escaneado
        claude_api.leer_pdf_escaneado = doble
        try:
            documento = await extraccion.extraer_pdf(pdf_sin_texto(3))
        finally:
            claude_api.leer_pdf_escaneado = original

        self.assertEqual(len(llamadas), 1)
        self.assertEqual(documento.origen, "claude-pdf")
        self.assertEqual(documento.texto, "Texto sacado del escaneo")
        self.assertIsNotNone(documento.uso)

    async def test_avisa_si_son_muchas_paginas(self) -> None:
        async def doble(datos):
            return "texto", None

        original = claude_api.leer_pdf_escaneado
        claude_api.leer_pdf_escaneado = doble
        try:
            documento = await extraccion.extraer_pdf(pdf_sin_texto(120))
        finally:
            claude_api.leer_pdf_escaneado = original

        self.assertTrue(documento.avisos, "120 paginas escaneadas tienen que avisar")


# ---------------------------------------------------------------------------
# Almacenamiento de documentos
# ---------------------------------------------------------------------------


class GuardarDocumentos(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    async def test_guardar_y_listar(self) -> None:
        await almacen.guardar_documento("tarifas", "contenido", 120, "plano")
        self.assertEqual(almacen.listar_documentos(), ["tarifas"])
        self.assertEqual(almacen.leer_documento("tarifas"), "contenido")
        self.assertEqual(almacen.metadatos_de("tarifas")["tokens"], 120)

    async def test_nunca_duplica(self) -> None:
        self.assertFalse(await almacen.guardar_documento("tarifas", "v1", 10, "plano"))
        sobrescrito = await almacen.guardar_documento("tarifas", "v2", 20, "plano")
        self.assertTrue(sobrescrito)
        self.assertEqual(almacen.listar_documentos(), ["tarifas"])
        self.assertEqual(almacen.leer_documento("tarifas"), "v2")
        self.assertEqual(almacen.total_tokens(), 20)

    async def test_orden_estable(self) -> None:
        """De este orden depende que la cache del system funcione."""
        for nombre in ("zeta", "alfa", "manual", "beta"):
            await almacen.guardar_documento(nombre, "x", 1, "plano")
        self.assertEqual(almacen.listar_documentos(), ["alfa", "beta", "manual", "zeta"])
        self.assertEqual(almacen.listar_documentos(), sorted(almacen.listar_documentos()))

    async def test_borrar(self) -> None:
        await almacen.guardar_documento("tarifas", "x", 10, "plano")
        await almacen.guardar_documento("manual", "y", 5, "plano")
        self.assertTrue(await almacen.borrar_documento("tarifas"))
        self.assertEqual(almacen.listar_documentos(), ["manual"])
        self.assertEqual(almacen.total_tokens(), 5)
        self.assertFalse(await almacen.borrar_documento("tarifas"))

    async def test_total_de_tokens(self) -> None:
        await almacen.guardar_documento("a", "x", 1000, "plano")
        await almacen.guardar_documento("b", "y", 2500, "plano")
        self.assertEqual(almacen.total_tokens(), 3500)


# ---------------------------------------------------------------------------
# Costes
# ---------------------------------------------------------------------------


class CalculoDeCostes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        limpiar_volume()

    def test_precio_de_entrada_y_salida(self) -> None:
        # Un millon de tokens de entrada son 2 dolares, y de salida 10.
        self.assertAlmostEqual(costes.coste_llamada(entrada=1_000_000), 2.00, places=6)
        self.assertAlmostEqual(costes.coste_llamada(salida=1_000_000), 10.00, places=6)

    def test_precio_de_la_cache(self) -> None:
        self.assertAlmostEqual(costes.coste_llamada(cache_lectura=1_000_000), 0.20, places=6)
        # Con TTL de 1 hora la escritura son 4 dolares por millon.
        self.assertAlmostEqual(
            costes.coste_llamada(cache_escritura=1_000_000, ttl="1h"), 4.00, places=6
        )
        self.assertAlmostEqual(
            costes.coste_llamada(cache_escritura=1_000_000, ttl="5m"), 2.50, places=6
        )

    def test_leer_la_cache_sale_mucho_mas_barato(self) -> None:
        caliente, frio = costes.estimar_pregunta(50_000)
        self.assertLess(caliente, frio)
        self.assertLess(caliente, 0.02)  # menos de dos centimos de dolar

    def test_en_euros_habla_como_un_empresario(self) -> None:
        self.assertEqual(costes.en_euros(0.0001), "menos de 1 céntimo")
        self.assertIn("céntimos", costes.en_euros(0.15))
        self.assertIn("euros", costes.en_euros(5.0))

    async def test_acumula_el_gasto(self) -> None:
        class Uso:
            input_tokens = 1_000_000
            output_tokens = 0
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0

        await costes.registrar_uso(Uso(), "prueba")
        await costes.registrar_uso(Uso(), "prueba")
        self.assertAlmostEqual(costes.gasto_del_mes(), 4.00, places=4)
        datos = almacen.leer_json(almacen.FICHERO_USO, almacen.USO_POR_DEFECTO)
        self.assertEqual(datos["peticiones"], 2)
        self.assertEqual(datos["periodo"], costes.periodo_actual())

    async def test_el_contador_se_reinicia_al_cambiar_de_mes(self) -> None:
        datos = dict(almacen.USO_POR_DEFECTO)
        datos.update({"periodo": "2001-01", "coste_usd": 99.0, "peticiones": 500})
        await almacen.guardar_json(almacen.FICHERO_USO, datos)
        self.assertEqual(costes.gasto_del_mes(), 0.0)

        class Uso:
            input_tokens = 1_000_000
            output_tokens = 0
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0

        await costes.registrar_uso(Uso(), "prueba")
        self.assertAlmostEqual(costes.gasto_del_mes(), 2.00, places=4)


def tearDownModule() -> None:
    shutil.rmtree(_TEMPORAL, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
