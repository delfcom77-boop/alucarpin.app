"""Modelo de tareas compartido por la app y el escritorio."""
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from unicodedata import combining, normalize


CAMPOS = (
    "id", "titulo", "tipo", "cliente", "obra", "notas", "fecha_prevista",
    "prioridad", "estado", "creado_en", "actualizado_en", "hecha_en", "version",
)
EDITABLES = CAMPOS[1:9]
TIPOS = ("Otro", "Llamada", "Presupuesto", "Material", "Visita")
PRIORIDADES = ("Normal", "Alta")


class TareaInvalida(ValueError):
    pass


class TareaModificada(RuntimeError):
    pass


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def inicializar_tareas(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS tareas ("
        "id TEXT PRIMARY KEY, titulo TEXT NOT NULL, tipo TEXT NOT NULL, "
        "cliente TEXT NOT NULL, obra TEXT NOT NULL, notas TEXT NOT NULL, "
        "fecha_prevista TEXT NOT NULL, prioridad TEXT NOT NULL, estado TEXT NOT NULL, "
        "creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL, hecha_en TEXT NOT NULL, "
        "version INTEGER NOT NULL CHECK (version > 0))"
    )
    if hasattr(db, "db"):
        db.execute("ALTER TABLE tareas ENABLE ROW LEVEL SECURITY")


def validar_tarea(datos):
    limites = {"titulo": 240, "cliente": 160, "obra": 300, "notas": 4000}
    valores = {}
    for campo, limite in limites.items():
        texto = datos.get(campo, "")
        if not isinstance(texto, str) or len(texto.strip()) > limite:
            raise TareaInvalida(f"Revisa {campo}: admite hasta {limite} caracteres.")
        valores[campo] = texto.strip()
    if not valores["titulo"]:
        raise TareaInvalida("Escribe lo que tienes que hacer.")
    for campo, opciones, defecto in (
        ("tipo", TIPOS, "Otro"), ("prioridad", PRIORIDADES, "Normal"),
        ("estado", ("Pendiente", "Hecha"), "Pendiente"),
    ):
        valor = datos.get(campo, defecto)
        if valor not in opciones:
            raise TareaInvalida(f"El valor de {campo} no es valido.")
        valores[campo] = valor
    fecha = datos.get("fecha_prevista", "")
    if not isinstance(fecha, str):
        raise TareaInvalida("La fecha prevista no es valida.")
    if fecha:
        try:
            if date.fromisoformat(fecha).isoformat() != fecha:
                raise ValueError
        except ValueError as error:
            raise TareaInvalida("La fecha prevista debe tener formato AAAA-MM-DD.") from error
    valores["fecha_prevista"] = fecha
    return valores


def identificador_tarea(valor):
    try:
        return str(UUID(str(valor)))
    except (ValueError, TypeError, AttributeError) as error:
        raise TareaInvalida("La referencia de tarea no es valida.") from error


def convertir_fila(fila):
    if fila is None:
        return None
    if hasattr(fila, "keys"):
        return {campo: fila[campo] for campo in CAMPOS}
    return dict(zip(CAMPOS, fila))


def obtener_tarea(db, ident):
    return convertir_fila(db.execute(
        "SELECT " + ",".join(CAMPOS) + " FROM tareas WHERE id=?", (ident,)
    ).fetchone())


def listar_tareas(db):
    return [convertir_fila(fila) for fila in db.execute(
        "SELECT " + ",".join(CAMPOS) + " FROM tareas ORDER BY "
        "CASE WHEN estado='Hecha' THEN 1 ELSE 0 END, "
        "CASE WHEN fecha_prevista='' THEN '9999-12-31' ELSE fecha_prevista END, "
        "CASE WHEN prioridad='Alta' THEN 0 ELSE 1 END, creado_en, id"
    ).fetchall()]


def guardar_tarea(db, datos, ident=None, version=None):
    valores = validar_tarea(datos)
    ident = identificador_tarea(ident) if ident else str(uuid4())
    anterior = obtener_tarea(db, ident)
    sello = ahora()
    if version is None:
        if anterior:
            if all(anterior[c] == valores[c] for c in EDITABLES):
                return anterior
            raise TareaModificada("Esta tarea ya existe con otro contenido. Recarga el listado.")
        tarea = dict(valores, id=ident, creado_en=sello, actualizado_en=sello,
                     hecha_en=sello if valores["estado"] == "Hecha" else "", version=1)
        db.execute(
            "INSERT INTO tareas (" + ",".join(CAMPOS) + ") VALUES ("
            + ",".join("?" for _ in CAMPOS) + ") ON CONFLICT(id) DO NOTHING",
            tuple(tarea[c] for c in CAMPOS),
        )
        actual = obtener_tarea(db, ident)
        if actual != tarea:
            if actual and all(actual[c] == valores[c] for c in EDITABLES):
                return actual
            raise TareaModificada("La tarea ha cambiado. Recarga el listado.")
        return tarea
    if not anterior or anterior["version"] != version:
        raise TareaModificada("La tarea ha cambiado en otro dispositivo. Recarga antes de guardar.")
    hecha = (anterior["hecha_en"] if anterior["estado"] == "Hecha" else sello) if valores["estado"] == "Hecha" else ""
    tarea = dict(valores, id=ident, creado_en=anterior["creado_en"],
                 actualizado_en=sello, hecha_en=hecha, version=version + 1)
    resultado = db.execute(
        "UPDATE tareas SET " + ",".join(c + "=?" for c in CAMPOS if c != "id")
        + " WHERE id=? AND version=?",
        tuple(tarea[c] for c in CAMPOS if c != "id") + (ident, version),
    )
    if resultado.rowcount != 1:
        raise TareaModificada("La tarea ha cambiado. No se ha sobrescrito; recarga el listado.")
    return tarea


def filtrar_tareas(tareas, filtro="Pendientes", busqueda="", tipo="", prioridad="", hoy=None):
    hoy = (hoy or date.today()).isoformat()
    def normalizar(texto):
        return "".join(c for c in normalize("NFD", texto.casefold()) if not combining(c))

    consulta = normalizar(busqueda.strip())
    resultado = []
    for tarea in tareas:
        hecha = tarea["estado"] == "Hecha"
        fecha = tarea["fecha_prevista"]
        if filtro == "Pendientes" and hecha:
            continue
        if filtro == "Hechas" and not hecha:
            continue
        if filtro == "Hoy" and (hecha or fecha != hoy):
            continue
        if filtro == "Atrasadas" and (hecha or not fecha or fecha >= hoy):
            continue
        if tipo and tarea["tipo"] != tipo or prioridad and tarea["prioridad"] != prioridad:
            continue
        if consulta and consulta not in normalizar(" ".join(tarea[c] for c in ("titulo", "cliente", "obra", "notas"))):
            continue
        resultado.append(tarea)
    return resultado
