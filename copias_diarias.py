"""Copia diaria de Alucarpin a un directorio privado del usuario Windows."""

import argparse
import ctypes
import csv
from ctypes import wintypes
from datetime import datetime
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from xml.sax.saxutils import escape
import zipfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ORIGEN = "https://alucarpin-app.onrender.com"
CARPETA = Path.home() / "AlucarpinCopias"
DESTINO_CREDENCIAL = "AlucarpinAppCopiaDiaria"
DESTINO_CLAVE_CIFRADO = "AlucarpinCopiaCifrada"
RETENCION_DIAS = 30
TAREA = "Alucarpin - copia diaria"
MAX_BYTES = 256 * 1024 * 1024
MAGIA_CIFRADO = b"ALUCARPIN-ENCRYPTED-BACKUP\x01"
ITERACIONES_KDF = 600_000
MIN_LONGITUD_CLAVE = 16


class ErrorCopia(RuntimeError):
    pass


class CredencialNoEncontrada(ErrorCopia):
    pass


class ClaveCifradoNoEncontrada(ErrorCopia):
    pass


if os.name == "nt":
    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _WINCRED = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    _WINCRED.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    _WINCRED.CredWriteW.restype = wintypes.BOOL
    _WINCRED.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    _WINCRED.CredReadW.restype = wintypes.BOOL
    _WINCRED.CredFree.argtypes = [ctypes.c_void_p]
    _WINCRED.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _WINCRED.CredDeleteW.restype = wintypes.BOOL


def guardar_credencial(usuario, contrasena):
    if os.name != "nt":
        raise ErrorCopia("La copia programada requiere Windows.")
    blob = ctypes.create_string_buffer(contrasena.encode("utf-16-le"))
    credencial = CREDENTIALW(
        Flags=0, Type=1, TargetName=DESTINO_CREDENCIAL, Comment="Acceso para copia de solo lectura",
        LastWritten=wintypes.FILETIME(),                 CredentialBlobSize=len(contrasena.encode("utf-16-le")),
        CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte)),
        Persist=2, AttributeCount=0, Attributes=None, TargetAlias=None, UserName=usuario,
    )
    if not _WINCRED.CredWriteW(ctypes.byref(credencial), 0):
        raise ErrorCopia("Windows no pudo guardar el acceso en el Administrador de credenciales.")


def leer_credencial():
    if os.name != "nt":
        raise ErrorCopia("La copia programada requiere Windows.")
    puntero = ctypes.POINTER(CREDENTIALW)()
    if not _WINCRED.CredReadW(DESTINO_CREDENCIAL, 1, 0, ctypes.byref(puntero)):
        if ctypes.get_last_error() == 1168:
            raise CredencialNoEncontrada("Falta configurar el acceso en el Administrador de credenciales.")
        raise ErrorCopia("Windows no pudo leer el acceso del Administrador de credenciales.")
    try:
        credencial = puntero.contents
        contrasena = ctypes.string_at(credencial.CredentialBlob, credencial.CredentialBlobSize).decode("utf-16-le")
        return credencial.UserName, contrasena
    finally:
        _WINCRED.CredFree(puntero)


def borrar_credencial():
    if os.name != "nt":
        raise ErrorCopia("La copia programada requiere Windows.")
    if not _WINCRED.CredDeleteW(DESTINO_CREDENCIAL, 1, 0) and ctypes.get_last_error() != 1168:
        raise ErrorCopia("Windows no pudo retirar el acceso del Administrador de credenciales.")


def guardar_clave_cifrado(clave):
    if os.name != "nt":
        raise ErrorCopia("El cifrado programado requiere Windows.")
    contenido = clave.encode("utf-16-le")
    blob = ctypes.create_string_buffer(contenido)
    credencial = CREDENTIALW(
        Flags=0, Type=1, TargetName=DESTINO_CLAVE_CIFRADO,
        Comment="Clave de cifrado para copias Alucarpin en OneDrive",
        LastWritten=wintypes.FILETIME(), CredentialBlobSize=len(contenido),
        CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte)),
        Persist=2, AttributeCount=0, Attributes=None, TargetAlias=None,
        UserName="Alucarpin copia cifrada",
    )
    if not _WINCRED.CredWriteW(ctypes.byref(credencial), 0):
        raise ErrorCopia("Windows no pudo guardar la clave de cifrado.")


def leer_clave_cifrado():
    if os.name != "nt":
        raise ErrorCopia("El cifrado programado requiere Windows.")
    puntero = ctypes.POINTER(CREDENTIALW)()
    if not _WINCRED.CredReadW(DESTINO_CLAVE_CIFRADO, 1, 0, ctypes.byref(puntero)):
        if ctypes.get_last_error() == 1168:
            raise ClaveCifradoNoEncontrada("Falta configurar la clave para las copias cifradas de OneDrive.")
        raise ErrorCopia("Windows no pudo leer la clave de cifrado.")
    try:
        credencial = puntero.contents
        return ctypes.string_at(
            credencial.CredentialBlob, credencial.CredentialBlobSize,
        ).decode("utf-16-le")
    finally:
        _WINCRED.CredFree(puntero)


def borrar_clave_cifrado():
    if os.name != "nt":
        raise ErrorCopia("El cifrado programado requiere Windows.")
    if not _WINCRED.CredDeleteW(DESTINO_CLAVE_CIFRADO, 1, 0) and ctypes.get_last_error() != 1168:
        raise ErrorCopia("Windows no pudo retirar la clave de cifrado.")


def cifrar_datos(datos, clave):
    sal = os.urandom(16)
    nonce = os.urandom(12)
    cabecera = MAGIA_CIFRADO + sal + nonce
    derivacion = PBKDF2HMAC(
        algorithm=SHA256(), length=32, salt=sal, iterations=ITERACIONES_KDF,
    )
    clave_aes = derivacion.derive(clave.encode("utf-8"))
    return cabecera + AESGCM(clave_aes).encrypt(nonce, datos, cabecera)


def descifrar_datos(datos, clave):
    longitud_cabecera = len(MAGIA_CIFRADO) + 16 + 12
    if len(datos) <= longitud_cabecera + 16 or not datos.startswith(MAGIA_CIFRADO):
        raise ErrorCopia("El archivo no es una copia cifrada de Alucarpin compatible.")
    cabecera = datos[:longitud_cabecera]
    sal = cabecera[len(MAGIA_CIFRADO):len(MAGIA_CIFRADO) + 16]
    nonce = cabecera[-12:]
    derivacion = PBKDF2HMAC(
        algorithm=SHA256(), length=32, salt=sal, iterations=ITERACIONES_KDF,
    )
    clave_aes = derivacion.derive(clave.encode("utf-8"))
    try:
        contenido = AESGCM(clave_aes).decrypt(nonce, datos[longitud_cabecera:], cabecera)
    except InvalidTag as error:
        raise ErrorCopia("La clave es incorrecta o la copia cifrada está dañada.") from error
    comprobar_zip(contenido)
    return contenido


def carpeta_onedrive():
    candidatos = (
        os.environ.get("OneDriveCommercial"),
        os.environ.get("OneDriveConsumer"),
        os.environ.get("OneDrive"),
    )
    for candidato in candidatos:
        if candidato and Path(candidato).is_dir():
            return Path(candidato) / "AlucarpinCopias"
    raise ErrorCopia("No se encuentra una carpeta OneDrive activa en este usuario de Windows.")


def sincronizar_copia_cifrada(archivo):
    datos = archivo.read_bytes()
    comprobar_zip(datos)
    clave = leer_clave_cifrado()
    carpeta = carpeta_onedrive()
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{archivo.name}.enc"
    if destino.exists():
        try:
            existente = descifrar_datos(destino.read_bytes(), clave)
        except (OSError, ErrorCopia):
            existente = b""
        if existente == datos:
            recortar_cifradas(carpeta)
            print(f"Copia cifrada verificada en OneDrive: {destino.name}.")
            return
    cifrado = cifrar_datos(datos, clave)
    if descifrar_datos(cifrado, clave) != datos:
        raise ErrorCopia("No se pudo verificar la copia cifrada; OneDrive no se ha actualizado.")
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".copia-", suffix=".tmp", dir=carpeta, delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(cifrado)
            salida.flush()
            os.fsync(salida.fileno())
        temporal.replace(destino)
    except OSError as error:
        raise ErrorCopia(
            "No se pudo guardar la copia cifrada en la carpeta de OneDrive; la copia local se conserva."
        ) from error
    finally:
        if temporal and temporal.exists():
            temporal.unlink()
    recortar_cifradas(carpeta)
    print(f"Copia cifrada verificada en OneDrive: {destino.name}.")


def onedrive_activado():
    return (CARPETA / "onedrive_cifrado.activado").is_file()


def recortar_cifradas(carpeta):
    copias = sorted(
        carpeta.glob("alucarpin-aplicacion-????-??-??.zip.enc"),
        key=lambda p: p.name, reverse=True,
    )
    for antigua in copias[RETENCION_DIAS:]:
        try:
            antigua.unlink()
        except OSError as error:
            raise ErrorCopia(f"No se pudo aplicar la retención a {antigua.name} en OneDrive.") from error


def solicitud(url, token=None, cuerpo=None, timeout=180, error_401=None):
    cabeceras = {"Accept": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    datos = None
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return respuesta.status, respuesta.headers, respuesta.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            mensaje = error_401 or "La sesión no es válida. Vuelve a configurar la copia diaria."
            raise ErrorCopia(mensaje) from None
        if error.code == 403:
            raise ErrorCopia("La cuenta configurada no tiene permiso de administrador.") from None
        if error.code == 503:
            raise ErrorCopia("El servicio o la base central no está disponible; no se guardó ninguna copia.") from None
        raise ErrorCopia(f"El servidor rechazó la copia (HTTP {error.code}). No se guardó ningún archivo.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ErrorCopia("No se pudo conectar con Render; no se guardó ninguna copia.") from error


def comprobar_zip(datos):
    if not datos or len(datos) > MAX_BYTES or not zipfile.is_zipfile(io.BytesIO(datos)):
        raise ErrorCopia("La respuesta no es un ZIP de respaldo válido.")
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as paquete:
            if set(paquete.namelist()) != {"base.dump", "manifiesto.json"}:
                raise ErrorCopia("El ZIP no contiene el respaldo PostgreSQL esperado.")
            manifiesto = json.loads(paquete.read("manifiesto.json"))
            tamano = paquete.getinfo("base.dump").file_size
            if manifiesto.get("formato") != "alucarpin-respaldo" or manifiesto.get("version") != 1:
                raise ErrorCopia("El formato del respaldo no es compatible.")
            if manifiesto.get("alcance_copia") != "aplicacion" or manifiesto.get("motor") != "postgresql":
                raise ErrorCopia("El servidor no devolvió una copia PostgreSQL de los datos de la app.")
            if manifiesto.get("archivo") != "base.dump" or manifiesto.get("bytes") != tamano:
                raise ErrorCopia("El tamaño del respaldo no coincide con su manifiesto.")
            huella = hashlib.sha256(paquete.read("base.dump")).hexdigest()
            if manifiesto.get("sha256") != huella or not manifiesto.get("tablas"):
                raise ErrorCopia("La huella o el inventario del respaldo no son válidos.")
            return manifiesto
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as error:
        if isinstance(error, ErrorCopia):
            raise
        raise ErrorCopia("No se pudo comprobar la integridad del ZIP.") from error


def descargar_copia(forzar=False):
    CARPETA.mkdir(parents=True, exist_ok=True)
    hoy = datetime.now().strftime("%Y-%m-%d")
    existente = CARPETA / f"alucarpin-aplicacion-{hoy}.zip"
    if not forzar and existente.exists():
        try:
            comprobar_zip(existente.read_bytes())
        except (OSError, ErrorCopia):
            pass
        else:
            print("Hoy ya hay una copia válida guardada. No se genera otra.")
            if onedrive_activado():
                sincronizar_copia_cifrada(existente)
            return
    usuario, contrasena = leer_credencial()
    _, _, respuesta = solicitud(
        f"{ORIGEN}/login", cuerpo={"usuario": usuario, "password": contrasena}, timeout=30,
        error_401="Alucarpin rechazó el usuario o la contraseña. Comprueba que sean los mismos que usas para entrar en la app.",
    )
    try:
        token = json.loads(respuesta)["token"]
    except (ValueError, KeyError, TypeError) as error:
        raise ErrorCopia("La respuesta de inicio de sesión no es válida.") from error
    estado, cabeceras, contenido = solicitud(
        f"{ORIGEN}/copias-seguridad?alcance=aplicacion", token=token,
        error_401="El inicio de sesión se aceptó, pero Render rechazó la sesión al descargar. Vuelve a configurar e inténtalo otra vez.",
    )
    if estado != 200 or cabeceras.get_content_type() != "application/zip":
        raise ErrorCopia("Render no devolvió un archivo ZIP; no se guardó ninguna copia.")
    if cabeceras.get("X-Alucarpin-Alcance") != "aplicacion":
        raise ErrorCopia("El alcance de la copia no coincide; no se guardó ningún archivo.")
    if len(contenido) > MAX_BYTES:
        raise ErrorCopia("El archivo supera el límite permitido; no se guardó ninguna copia.")
    manifiesto = comprobar_zip(contenido)
    nombre = f"alucarpin-aplicacion-{hoy}.zip"
    archivo = CARPETA / nombre
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".copia-", suffix=".tmp", dir=CARPETA, delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        temporal.replace(archivo)
    except OSError as error:
        raise ErrorCopia("No se pudo guardar la copia local; no se eliminó ninguna copia anterior.") from error
    finally:
        if temporal and temporal.exists():
            temporal.unlink()
    recortar_antiguas()
    print(f"Copia válida guardada: {archivo.name} ({len(manifiesto['tablas'])} tablas).")
    if onedrive_activado():
        sincronizar_copia_cifrada(archivo)


def recortar_antiguas():
    copias = sorted(CARPETA.glob("alucarpin-aplicacion-????-??-??.zip"), key=lambda p: p.name, reverse=True)
    for antigua in copias[RETENCION_DIAS:]:
        try:
            antigua.unlink()
        except OSError as error:
            raise ErrorCopia(f"No se pudo aplicar la retención a {antigua.name}.") from error


def configurar():
    usuario = input("Usuario administrador de Alucarpin: ").strip()
    if not usuario:
        raise ErrorCopia("El nombre de usuario no puede estar vacío.")
    contrasena = getpass.getpass("Contraseña (no se mostrará ni se enviará al chat): ")
    if not contrasena:
        raise ErrorCopia("La contraseña no puede estar vacía.")
    anterior = None
    try:
        anterior = leer_credencial()
    except CredencialNoEncontrada:
        pass
    guardar_credencial(usuario, contrasena)
    try:
        descargar_copia(forzar=True)
    except Exception:
        if anterior:
            guardar_credencial(*anterior)
        else:
            borrar_credencial()
        raise
    registrar_tarea()
    print("Copia diaria preparada para las 21:00 y al iniciar sesión. Conserva 30 días.")


def copia_local_reciente():
    archivos = sorted(
        CARPETA.glob("alucarpin-aplicacion-????-??-??.zip"),
        key=lambda p: p.name, reverse=True,
    )
    for archivo in archivos:
        try:
            comprobar_zip(archivo.read_bytes())
        except (OSError, ErrorCopia):
            continue
        return archivo
    raise ErrorCopia("No hay una copia local válida para cifrar. Ejecuta primero una copia diaria.")


def configurar_cifrado_onedrive():
    carpeta_onedrive()
    try:
        leer_clave_cifrado()
    except ClaveCifradoNoEncontrada:
        clave = getpass.getpass("Frase para cifrar copias (mínimo 16 caracteres): ")
        if len(clave) < MIN_LONGITUD_CLAVE:
            raise ErrorCopia(f"La frase debe tener al menos {MIN_LONGITUD_CLAVE} caracteres.")
        confirmacion = getpass.getpass("Repite la frase de cifrado: ")
        if clave != confirmacion:
            raise ErrorCopia("Las frases no coinciden. No se ha guardado ninguna clave.")
        guardar_clave_cifrado(clave)
    else:
        print("Ya existe una clave de cifrado guardada en Windows; se conservará.")
    sincronizar_copia_cifrada(copia_local_reciente())
    try:
        (CARPETA / "onedrive_cifrado.activado").write_text(
            "Copia cifrada de Alucarpin activada.\n", encoding="utf-8",
        )
    except OSError as error:
        raise ErrorCopia("La copia cifrada está en OneDrive, pero no se pudo activar la sincronización diaria.") from error
    print(
        "Copia cifrada preparada. Guarda la frase de cifrado fuera de este PC: "
        "la necesitarás para recuperar los archivos desde OneDrive."
    )


def descifrar_archivo(archivo, destino, clave):
    contenido = descifrar_datos(archivo.read_bytes(), clave)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destino.open("xb") as salida:
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
    except FileExistsError as error:
        raise ErrorCopia("El archivo de destino ya existe; no se ha sobrescrito.") from error
    except OSError as error:
        try:
            destino.unlink(missing_ok=True)
        except OSError:
            pass
        raise ErrorCopia("No se pudo guardar el ZIP descifrado.") from error
    return destino


def registrar_tarea():
    if os.name != "nt":
        raise ErrorCopia("La programación solo está implementada para Windows.")
    ejecutable = Path(sys.executable).resolve()
    programa = Path(__file__).resolve()
    identidad = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True,
    ).stdout
    filas_identidad = list(csv.reader(identidad.splitlines()))
    if len(filas_identidad) != 1 or len(filas_identidad[0]) != 2:
        raise ErrorCopia("Windows no pudo identificar la cuenta actual para la tarea diaria.")
    sid = filas_identidad[0][1].strip()
    if not sid.startswith("S-") or any(not parte.isdigit() for parte in sid.split("-")[1:]):
        raise ErrorCopia("Windows devolvió un identificador de cuenta no válido para la tarea diaria.")
    ahora = datetime.now().astimezone()
    siguiente = ahora.replace(hour=21, minute=0, second=0, microsecond=0)
    if siguiente <= ahora:
        from datetime import timedelta
        siguiente += timedelta(days=1)
    boundary = siguiente.strftime("%Y-%m-%dT%H:%M:%S")
    tarea = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Copia diaria verificada de los datos de Alucarpin en este equipo.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger><StartBoundary>{boundary}</StartBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><Delay>PT5M</Delay></LogonTrigger>
  </Triggers>
  <Principals><Principal id="Autor"><UserId>{sid}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>true</StartWhenAvailable>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate><Enabled>true</Enabled><Hidden>false</Hidden>
    <RestartOnFailure><Interval>PT15M</Interval><Count>3</Count></RestartOnFailure>
    <ExecutionTimeLimit>PT20M</ExecutionTimeLimit><Priority>7</Priority>
  </Settings>
  <Actions Context="Autor"><Exec><Command>{escape(str(ejecutable))}</Command><Arguments>"{escape(str(programa))}" --ejecutar</Arguments><WorkingDirectory>{escape(str(CARPETA))}</WorkingDirectory></Exec></Actions>
</Task>"""
    CARPETA.mkdir(parents=True, exist_ok=True)
    descriptor, ruta = tempfile.mkstemp(prefix="tarea-alucarpin-", suffix=".xml", dir=CARPETA)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-16") as archivo:
            archivo.write(tarea)
        resultado = subprocess.run(
            ["schtasks.exe", "/Create", "/TN", TAREA, "/XML", ruta, "/F"],
            capture_output=True, text=True,
        )
        if resultado.returncode:
            detalle = (resultado.stderr or resultado.stdout).strip()
            if "acceso denegado" in detalle.casefold() or "access is denied" in detalle.casefold():
                raise ErrorCopia(
                    "Windows denegó el registro de la tarea. Vuelve a ejecutar el configurador "
                    "con el botón derecho → Ejecutar como administrador y acepta el aviso de Windows. "
                    "La copia inicial ya quedó guardada."
                )
            if detalle:
                raise ErrorCopia(
                    f"Windows no pudo registrar la tarea diaria: {detalle} "
                    "La copia inicial ya quedó guardada."
                )
            raise ErrorCopia("Windows no pudo registrar la tarea diaria. La copia inicial ya quedó guardada.")
    finally:
        Path(ruta).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Copia local diaria de Alucarpin; no cambia la base Supabase.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--configurar", action="store_true", help="Guarda el acceso localmente y programa la tarea diaria")
    grupo.add_argument("--ejecutar", action="store_true", help="Ejecuta una copia")
    grupo.add_argument(
        "--configurar-cifrado-onedrive", action="store_true",
        help="Prepara una copia cifrada en la carpeta OneDrive",
    )
    grupo.add_argument("--descifrar", type=Path, help="Descifra una copia OneDrive propia y confiable")
    parser.add_argument("--destino", type=Path, help="Ruta nueva donde guardar un ZIP descifrado")
    args = parser.parse_args()
    if args.destino and not args.descifrar:
        parser.error("--destino solo se usa con --descifrar.")
    try:
        if args.configurar:
            configurar()
        elif args.configurar_cifrado_onedrive:
            configurar_cifrado_onedrive()
        elif args.descifrar:
            destino = args.destino or args.descifrar.with_suffix("")
            clave = getpass.getpass("Frase de cifrado de la copia: ")
            ruta = descifrar_archivo(args.descifrar, destino, clave)
            print(f"Copia descifrada y validada: {ruta}")
        else:
            descargar_copia()
    except ErrorCopia as error:
        print(f"ERROR: {error}", file=sys.stderr)
        try:
            CARPETA.mkdir(parents=True, exist_ok=True)
            with (CARPETA / "copias_diarias.log").open("a", encoding="utf-8") as archivo:
                archivo.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} ERROR: {error}\n")
        except OSError:
            pass
        raise SystemExit(1) from error
    else:
        try:
            CARPETA.mkdir(parents=True, exist_ok=True)
            with (CARPETA / "copias_diarias.log").open("a", encoding="utf-8") as archivo:
                archivo.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} OK\n")
        except OSError as error:
            print(f"ERROR: No se pudo guardar el registro de la tarea: {error}", file=sys.stderr)
            raise SystemExit(1) from error


if __name__ == "__main__":
    main()
