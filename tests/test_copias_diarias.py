from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
import xml.etree.ElementTree as ET
import zipfile

import copias_diarias as copia


def zip_valido(alcance="aplicacion", motor="postgresql"):
    datos = b"dump"
    manifiesto = {
        "formato": "alucarpin-respaldo", "version": 1, "motor": motor,
        "alcance_copia": alcance, "archivo": "base.dump", "bytes": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest(), "tablas": {"public.obras": {"filas": 1}},
    }
    archivo = io.BytesIO()
    with zipfile.ZipFile(archivo, "w") as paquete:
        paquete.writestr("base.dump", datos)
        paquete.writestr("manifiesto.json", json.dumps(manifiesto))
    return archivo.getvalue()


class CopiasDiariasTests(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.carpeta = Path(carpeta.name)
        self.mensaje_zip = Message()
        self.mensaje_zip["Content-Type"] = "application/zip"
        self.mensaje_zip["X-Alucarpin-Alcance"] = "aplicacion"
        self.respuestas = [
            (200, Message(), json.dumps({"token": "temporal"}).encode()),
            (200, self.mensaje_zip, zip_valido()),
        ]

    def llamadas(self, *args, **kwargs):
        return self.respuestas.pop(0)

    def test_solicitud_envia_token_como_bearer(self):
        respuesta = MagicMock()
        respuesta.__enter__.return_value.status = 200
        respuesta.__enter__.return_value.headers = Message()
        respuesta.__enter__.return_value.read.return_value = b"ok"
        with patch.object(copia.urllib.request, "urlopen", return_value=respuesta) as abrir:
            copia.solicitud("https://ejemplo.invalid/recurso", token="token-de-prueba")
        peticion = abrir.call_args.args[0]
        self.assertEqual(peticion.get_header("Authorization"), "Bearer token-de-prueba")

    def test_cifrado_autentica_datos_y_rechaza_clave_o_contenido_alterado(self):
        datos = zip_valido()
        cifrado = copia.cifrar_datos(datos, "frase larga de prueba")
        self.assertNotEqual(cifrado, datos)
        self.assertEqual(copia.descifrar_datos(cifrado, "frase larga de prueba"), datos)
        with self.assertRaisesRegex(copia.ErrorCopia, "clave es incorrecta"):
            copia.descifrar_datos(cifrado, "otra frase")
        alterado = cifrado[:-1] + bytes([cifrado[-1] ^ 1])
        with self.assertRaisesRegex(copia.ErrorCopia, "dañada"):
            copia.descifrar_datos(alterado, "frase larga de prueba")

    def test_publica_solo_copia_cifrada_en_carpeta_onedrive(self):
        local = self.carpeta / "alucarpin-aplicacion-2026-10-06.zip"
        local.write_bytes(zip_valido())
        nube = self.carpeta / "OneDrive"
        nube.mkdir()
        with (patch.object(copia, "leer_clave_cifrado", return_value="frase de prueba suficientemente larga"),
              patch.object(copia, "carpeta_onedrive", return_value=nube / "AlucarpinCopias")):
            copia.sincronizar_copia_cifrada(local)
        resultado = nube / "AlucarpinCopias" / f"{local.name}.enc"
        self.assertTrue(resultado.is_file())
        self.assertNotEqual(resultado.read_bytes(), local.read_bytes())
        self.assertEqual(
            copia.descifrar_datos(resultado.read_bytes(), "frase de prueba suficientemente larga"),
            local.read_bytes(),
        )

    def test_configura_cifrado_sin_exponer_frase_y_activa_copia_diaria(self):
        local = self.carpeta / "alucarpin-aplicacion-2026-10-06.zip"
        local.write_bytes(zip_valido())
        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia, "leer_clave_cifrado", side_effect=copia.ClaveCifradoNoEncontrada("falta")),
              patch.object(copia.getpass, "getpass", side_effect=[
                  "una frase de prueba segura", "una frase de prueba segura",
              ]),
              patch.object(copia, "guardar_clave_cifrado") as guardar,
              patch.object(copia, "sincronizar_copia_cifrada") as sincronizar):
            copia.configurar_cifrado_onedrive()
        guardar.assert_called_once_with("una frase de prueba segura")
        sincronizar.assert_called_once_with(local)
        self.assertTrue((self.carpeta / "onedrive_cifrado.activado").is_file())

    def test_configuracion_rechaza_frase_de_cifrado_demasiado_corta(self):
        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia, "leer_clave_cifrado", side_effect=copia.ClaveCifradoNoEncontrada("falta")),
              patch.object(copia.getpass, "getpass", return_value="demasiado corta"),
              patch.object(copia, "guardar_clave_cifrado") as guardar,
              self.assertRaisesRegex(copia.ErrorCopia, "16 caracteres")):
            copia.configurar_cifrado_onedrive()
        guardar.assert_not_called()

    def test_descifrado_crea_zip_nuevo_sin_sobrescribir(self):
        cifrado = self.carpeta / "respaldo.zip.enc"
        destino = self.carpeta / "respaldo.zip"
        cifrado.write_bytes(copia.cifrar_datos(zip_valido(), "frase de prueba"))
        self.assertEqual(copia.descifrar_archivo(cifrado, destino, "frase de prueba"), destino)
        self.assertEqual(copia.comprobar_zip(destino.read_bytes())["motor"], "postgresql")
        with self.assertRaisesRegex(copia.ErrorCopia, "ya existe"):
            copia.descifrar_archivo(cifrado, destino, "frase de prueba")

    def test_solicitud_muestra_el_contexto_del_401_sin_detalles_de_credenciales(self):
        error = copia.urllib.error.HTTPError("https://ejemplo.invalid/login", 401, "Unauthorized", {}, None)
        self.addCleanup(error.close)
        with patch.object(copia.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(copia.ErrorCopia, "usuario o la contraseña") as contexto:
                copia.solicitud(
                    "https://ejemplo.invalid/login",
                    cuerpo={"usuario": "admin", "password": "no-imprimir"},
                    error_401="Alucarpin rechazó el usuario o la contraseña.",
                )
        self.assertNotIn("no-imprimir", str(contexto.exception))

    @unittest.skipUnless(__import__("os").name == "nt", "Windows Credential Manager solo existe en Windows")
    def test_windows_guarda_y_recupera_contrasena_sin_truncar(self):
        identificador = f"AlucarpinAppBackup-test-{id(self)}"
        with patch.object(copia, "DESTINO_CREDENCIAL", identificador):
            try:
                copia.guardar_credencial("usuario_prueba", "prueba-con-á-123")
                self.assertEqual(copia.leer_credencial(), ("usuario_prueba", "prueba-con-á-123"))
            finally:
                copia._WINCRED.CredDeleteW(identificador, 1, 0)

    def test_descarga_valida_conserva_zip_y_no_publica_credenciales(self):
        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia, "leer_credencial", return_value=("admin", "secreto")),
              patch.object(copia, "solicitud", side_effect=self.llamadas) as solicitar):
            copia.descargar_copia()
        archivos = list(self.carpeta.glob("alucarpin-aplicacion-*.zip"))
        self.assertEqual(len(archivos), 1)
        self.assertEqual(copia.comprobar_zip(archivos[0].read_bytes())["tablas"]["public.obras"]["filas"], 1)
        self.assertEqual(solicitar.call_args_list[0].kwargs["cuerpo"], {"usuario": "admin", "password": "secreto"})
        self.assertTrue(solicitar.call_args_list[1].kwargs["token"] == "temporal")

    def test_no_guarda_respuesta_que_no_sea_copia_aplicacion_postgres(self):
        for alcance, motor in (("completa", "postgresql"), ("aplicacion", "sqlite")):
            with self.subTest(alcance=alcance, motor=motor):
                self.respuestas = [
                    (200, Message(), json.dumps({"token": "temporal"}).encode()),
                    (200, self.mensaje_zip, zip_valido(alcance, motor)),
                ]
                with (patch.object(copia, "CARPETA", self.carpeta),
                      patch.object(copia, "leer_credencial", return_value=("admin", "secreto")),
                      patch.object(copia, "solicitud", side_effect=self.llamadas),
                      self.assertRaises(copia.ErrorCopia)):
                    copia.descargar_copia(forzar=True)
        self.assertEqual(list(self.carpeta.glob("*.zip")), [])

    def test_no_pisa_copia_hoy_valida_y_regenera_si_esta_corrupta(self):
        ruta = self.carpeta / f"alucarpin-aplicacion-{copia.datetime.now().strftime('%Y-%m-%d')}.zip"
        ruta.write_bytes(zip_valido())
        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia, "solicitud") as solicitar,
              patch.object(copia, "sincronizar_copia_cifrada") as sincronizar):
            copia.descargar_copia()
        solicitar.assert_not_called()
        sincronizar.assert_not_called()
        ruta.write_bytes(b"corrupta")
        self.respuestas = [
            (200, Message(), json.dumps({"token": "temporal"}).encode()),
            (200, self.mensaje_zip, zip_valido()),
        ]
        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia, "leer_credencial", return_value=("admin", "secreto")),
              patch.object(copia, "solicitud", side_effect=self.llamadas)):
            copia.descargar_copia()
        self.assertEqual(copia.comprobar_zip(ruta.read_bytes())["motor"], "postgresql")

    def test_retencion_se_ejecuta_solo_tras_respaldo_correcto(self):
        for dia in range(1, 32):
            (self.carpeta / f"alucarpin-aplicacion-2026-09-{dia:02}.zip").write_bytes(b"prueba")
        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia, "leer_credencial", return_value=("admin", "secreto")),
              patch.object(copia, "solicitud", side_effect=self.llamadas)):
            copia.descargar_copia(forzar=True)
        nombres = sorted(p.name for p in self.carpeta.glob("alucarpin-aplicacion-*.zip"))
        self.assertEqual(len(nombres), 30)
        self.assertNotIn("alucarpin-aplicacion-2026-09-01.zip", nombres)
        self.assertTrue(any(copia.datetime.now().strftime("%Y-%m-%d") in nombre for nombre in nombres))

    def test_fallo_red_y_respuesta_no_zip_no_crean_archivos(self):
        casos = (
            lambda *args, **kwargs: self.fallar_red(),
            self.login_valido_html_invalido,
        )
        for indice, respuesta in enumerate(casos):
            if indice == 1:
                self.respuestas = [(200, Message(), json.dumps({"token": "temporal"}).encode())]
            with (patch.object(copia, "CARPETA", self.carpeta),
                  patch.object(copia, "leer_credencial", return_value=("admin", "secreto")),
                  patch.object(copia, "solicitud", side_effect=respuesta),
                  self.assertRaises((copia.ErrorCopia, RuntimeError))):
                copia.descargar_copia(forzar=True)
        self.assertEqual(list(self.carpeta.glob("*.zip")), [])

    @staticmethod
    def fallar_red():
        raise copia.ErrorCopia("Sin red")

    def login_valido_html_invalido(self, *args, **kwargs):
        if self.respuestas:
            return self.respuestas.pop(0)
        return 200, Message(), b"<html>fallo</html>"

    def test_ventana_de_reconfiguracion_no_imprime_credenciales(self):
        with (patch.object(copia, "input", return_value="admin"),
              patch.object(copia.getpass, "getpass", return_value="no-imprimir"),
              patch.object(copia, "leer_credencial", side_effect=copia.CredencialNoEncontrada("sin credencial")),
              patch.object(copia, "guardar_credencial") as guardar,
              patch.object(copia, "descargar_copia") as descargar,
              patch.object(copia, "registrar_tarea") as tarea):
            copia.configurar()
        guardar.assert_called_once_with("admin", "no-imprimir")
        descargar.assert_called_once_with(forzar=True)
        tarea.assert_called_once()

    def test_fallo_al_registrar_tarea_conserva_la_credencial_nueva_validada(self):
        anterior = ("admin-anterior", "clave-anterior")
        with (patch.object(copia, "input", return_value="admin-nuevo"),
              patch.object(copia.getpass, "getpass", return_value="clave-nueva"),
              patch.object(copia, "leer_credencial", return_value=anterior),
              patch.object(copia, "guardar_credencial") as guardar,
              patch.object(copia, "descargar_copia"),
              patch.object(copia, "registrar_tarea", side_effect=RuntimeError("error de tarea")),
              self.assertRaisesRegex(RuntimeError, "error de tarea")):
            copia.configurar()
        guardar.assert_called_once_with("admin-nuevo", "clave-nueva")

    def test_fallo_de_descarga_sin_credencial_previa_elimina_credencial_nueva(self):
        with (patch.object(copia, "input", return_value="admin"),
              patch.object(copia.getpass, "getpass", return_value="clave"),
              patch.object(copia, "leer_credencial", side_effect=copia.CredencialNoEncontrada("sin credencial")),
              patch.object(copia, "guardar_credencial") as guardar,
              patch.object(copia, "descargar_copia", side_effect=RuntimeError("fallo de descarga")),
              patch.object(copia, "registrar_tarea") as tarea,
              patch.object(copia, "borrar_credencial") as borrar,
              self.assertRaisesRegex(RuntimeError, "fallo de descarga")):
            copia.configurar()
        guardar.assert_called_once_with("admin", "clave")
        borrar.assert_called_once_with()
        tarea.assert_not_called()

    def test_tarea_windows_define_horario_y_reintentos_de_inicio_de_sesion(self):
        raiz_xml = []

        def ejecutar(comando, **kwargs):
            if comando[0] == "whoami":
                return Mock(stdout='"PC\\\\usuario","S-1-5-21-123"\r\n')
            raiz_xml.append(Path(comando[5]).read_text(encoding="utf-16"))
            return Mock(returncode=0)

        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia.subprocess, "run", side_effect=ejecutar)):
            copia.registrar_tarea()

        raiz = ET.fromstring(raiz_xml[0])
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        calendario = raiz.find(".//t:CalendarTrigger", ns)
        inicio_sesion = raiz.find(".//t:LogonTrigger", ns)
        self.assertIsNotNone(calendario)
        self.assertIsNotNone(inicio_sesion)
        self.assertEqual(inicio_sesion.findtext("t:Delay", namespaces=ns), "PT5M")
        settings = raiz.find("t:Settings", ns)
        self.assertEqual(settings.findtext("t:RestartOnFailure/t:Interval", namespaces=ns), "PT15M")
        self.assertEqual(settings.findtext("t:RestartOnFailure/t:Count", namespaces=ns), "3")

    def test_acceso_denegado_indica_ejecutar_configurador_como_administrador(self):
        def ejecutar(comando, **kwargs):
            if comando[0] == "whoami":
                return Mock(stdout='"PC\\\\usuario","S-1-5-21-123"\r\n')
            return Mock(returncode=1, stderr="Error: Acceso denegado.")

        with (patch.object(copia, "CARPETA", self.carpeta),
              patch.object(copia.subprocess, "run", side_effect=ejecutar),
              self.assertRaisesRegex(copia.ErrorCopia, "Ejecutar como administrador")):
            copia.registrar_tarea()


if __name__ == "__main__":
    unittest.main()
