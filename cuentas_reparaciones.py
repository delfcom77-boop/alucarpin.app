"""Movimientos independientes de cobro y coste de una reparacion."""

from decimal import Decimal, InvalidOperation
from uuid import uuid4


COLUMNAS = (
    "id", "trabajo_id", "clase", "fecha", "importe", "importe_pagado",
    "forma_pago", "concepto", "proveedor", "categoria", "version",
    "version_base", "eliminado", "historico",
)


def filas(db, sql, parametros=()):
    cursor = db.execute(sql, parametros)
    nombres = [columna[0] for columna in cursor.description]
    return [dict(fila) if hasattr(fila, "keys") else dict(zip(nombres, fila))
            for fila in cursor.fetchall()]


def inicializar_cuentas(db, postgres=False):
    if postgres:
        columnas = {fila["column_name"] for fila in filas(
            db, "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='trabajos_propios'")}
    else:
        columnas = {fila["name"] for fila in filas(db, "PRAGMA table_info(trabajos_propios)")}
    if "cuenta_uid" not in columnas:
        db.execute("ALTER TABLE trabajos_propios ADD COLUMN cuenta_uid TEXT")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trabajo_cuenta_uid "
        "ON trabajos_propios(cuenta_uid) WHERE cuenta_uid IS NOT NULL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_reparaciones (
            id TEXT PRIMARY KEY,
            trabajo_id BIGINT NOT NULL REFERENCES trabajos_propios(id),
            clase TEXT NOT NULL CHECK(clase IN ('ingreso','gasto')),
            fecha TEXT,
            importe DOUBLE PRECISION NOT NULL CHECK(importe >= 0),
            importe_pagado DOUBLE PRECISION NOT NULL DEFAULT 0
                CHECK(importe_pagado >= 0 AND importe_pagado <= importe),
            forma_pago TEXT NOT NULL,
            concepto TEXT NOT NULL DEFAULT '',
            proveedor TEXT NOT NULL DEFAULT '',
            categoria TEXT NOT NULL DEFAULT 'Otros',
            version INTEGER NOT NULL DEFAULT 1,
            version_base INTEGER NOT NULL DEFAULT 0,
            eliminado INTEGER NOT NULL DEFAULT 0,
            historico INTEGER NOT NULL DEFAULT 0
        )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_movimientos_reparacion "
        "ON movimientos_reparaciones(trabajo_id, clase)")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cobro_historico_reparacion "
        "ON movimientos_reparaciones(trabajo_id) WHERE historico=1")


def dinero(valor):
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Introduce una cantidad numerica valida.") from error
    if not numero.is_finite() or numero < 0:
        raise ValueError("La cantidad debe ser finita y no negativa.")
    try:
        redondeado = numero.quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise ValueError("La cantidad es demasiado grande.") from error
    if numero != redondeado:
        raise ValueError("La cantidad debe tener como maximo dos decimales.")
    return float(numero)


def movimientos(db, trabajo_id, incluir_borrados=False):
    return filas(db, "SELECT * FROM movimientos_reparaciones WHERE trabajo_id=? "
                 + ("" if incluir_borrados else "AND eliminado=0 ")
                 + "ORDER BY fecha,id", (trabajo_id,))


def resumenes_cuentas(db, trabajos):
    grupos = {}
    for movimiento in filas(db, "SELECT * FROM movimientos_reparaciones"):
        grupos.setdefault(movimiento["trabajo_id"], []).append(movimiento)
    return {t["id"]: resumen_cuenta(db, t, grupos.get(t["id"], [])) for t in trabajos}


def resumen_cuenta(db, trabajo, registros=None):
    if registros is None:
        registros = movimientos(db, trabajo["id"], True)
    ingresos = [r for r in registros if r["clase"] == "ingreso"]
    historico = not ingresos and trabajo.get("estado_cobro") == "Cobrado"
    cobrado = (dinero(trabajo.get("importe") or 0) if historico else
               sum(r["importe"] for r in ingresos if not r["eliminado"]))
    cobrado = round(cobrado, 2)
    gastos = [r for r in registros if r["clase"] == "gasto" and not r["eliminado"]]
    total = dinero(trabajo.get("importe") or 0)
    costes = sum(r["importe"] for r in gastos)
    return {
        "cobrado": round(cobrado, 2), "gastos": round(costes, 2),
        "gastos_pagados": round(sum(r["importe_pagado"] for r in gastos), 2),
        "pendiente_cobro": round(max(total - cobrado, 0), 2),
        "beneficio": round(total - costes, 2), "historico": historico,
        "tiene_historial": bool(ingresos),
        "estado_cobro": "Cobrado" if cobrado >= total and cobrado > 0 else
                        "Parcial" if cobrado > 0 else "No cobrado",
    }


def materializar_historico(db, trabajo):
    if not resumen_cuenta(db, trabajo)["historico"]:
        return
    db.execute(
        "INSERT INTO movimientos_reparaciones "
        "(id,trabajo_id,clase,fecha,importe,importe_pagado,forma_pago,concepto,historico) "
        "VALUES (?,?,'ingreso',?,?,0,?,'Cobro historico anterior al historial',1)",
        (str(uuid4()), trabajo["id"], str(trabajo.get("fecha_cobro") or "") or None,
         dinero(trabajo.get("importe") or 0), trabajo.get("forma_pago") or "No indicada"))


def guardar_movimiento(db, trabajo, datos, ident=None, version=None):
    from datetime import date

    clase = datos["clase"]
    if clase not in ("ingreso", "gasto"):
        raise ValueError("Tipo de movimiento no valido.")
    fecha = str(datos["fecha"])
    date.fromisoformat(fecha)
    importe = dinero(datos["importe"])
    pagado = dinero(datos.get("importe_pagado", 0)) if clase == "gasto" else 0
    if importe <= 0 or pagado > importe:
        raise ValueError("El importe debe ser mayor que cero y el pago no superar el gasto.")
    forma = datos["forma_pago"]
    if forma not in ("Transferencia", "Efectivo"):
        raise ValueError("Forma de pago no valida.")
    concepto = str(datos.get("concepto", "")).strip()
    if clase == "gasto" and not concepto:
        raise ValueError("Indica el concepto del gasto.")
    valores = (fecha, importe, pagado, forma, concepto,
               str(datos.get("proveedor", "")).strip(), str(datos.get("categoria", "Otros")))
    if not ident:
        if clase == "ingreso":
            materializar_historico(db, trabajo)
        ident = str(uuid4())
        db.execute(
            "INSERT INTO movimientos_reparaciones "
            "(id,trabajo_id,clase,fecha,importe,importe_pagado,forma_pago,concepto,proveedor,categoria) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", (ident, trabajo["id"], clase, *valores))
    else:
        cursor = db.execute(
            "UPDATE movimientos_reparaciones SET fecha=?,importe=?,importe_pagado=?,"
            "forma_pago=?,concepto=?,proveedor=?,categoria=?,version=version+1 "
            "WHERE id=? AND trabajo_id=? AND clase=? AND version=? AND eliminado=0",
            (*valores, ident, trabajo["id"], clase, version))
        if cursor.rowcount != 1:
            raise ValueError("El movimiento ha cambiado. Actualiza el historial antes de editarlo.")
    return ident


def borrar_movimiento(db, trabajo_id, ident, version):
    cursor = db.execute(
        "UPDATE movimientos_reparaciones SET eliminado=1,version=version+1 "
        "WHERE id=? AND trabajo_id=? AND version=? AND eliminado=0",
        (ident, trabajo_id, version))
    if cursor.rowcount != 1:
        raise ValueError("El movimiento ha cambiado. Actualiza el historial antes de borrarlo.")
