"""Un coste por ayudante y fecha; la imputacion no crea otro gasto ni un pago."""

from datetime import date


def filas(db, sql, parametros=()):
    cursor = db.execute(sql, parametros)
    nombres = [c[0] for c in cursor.description]
    return [dict(f) if hasattr(f, "keys") else dict(zip(nombres, f)) for f in cursor.fetchall()]


def inicializar_imputaciones(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS imputaciones_ayudantes ("
        "ayudante_id BIGINT NOT NULL REFERENCES ayudantes(id) ON DELETE RESTRICT,"
        "fecha DATE NOT NULL, destino TEXT NOT NULL CHECK(destino IN ('alucarpin','faena','presupuesto','propio')),"
        "faena_id BIGINT REFERENCES faenas(id) ON DELETE RESTRICT,"
        "presupuesto_id BIGINT REFERENCES presupuestos(id) ON DELETE RESTRICT,"
        "trabajo_id BIGINT REFERENCES trabajos_propios(id) ON DELETE RESTRICT,"
        "version INTEGER NOT NULL DEFAULT 1, actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "PRIMARY KEY(ayudante_id,fecha),"
        "CHECK((destino='alucarpin' AND faena_id IS NULL AND presupuesto_id IS NULL AND trabajo_id IS NULL)"
        " OR (destino='faena' AND faena_id IS NOT NULL AND presupuesto_id IS NULL AND trabajo_id IS NULL)"
        " OR (destino='presupuesto' AND presupuesto_id IS NOT NULL AND faena_id IS NULL AND trabajo_id IS NULL)"
        " OR (destino='propio' AND trabajo_id IS NOT NULL AND faena_id IS NULL AND presupuesto_id IS NULL)))"
    )


def agrupar_costes(fichajes, pagos, gastos, nombres, imputaciones=()):
    por_id = {f["id"]: f for f in fichajes}
    por_dia = {}
    for p in pagos:
        f = por_id.get(p["fichaje_id"])
        if f:
            por_dia.setdefault((f["ayudante_id"], str(f["fecha"])), []).append(p)
    grupos = {}
    for f in fichajes:
        grupos.setdefault((f["ayudante_id"], str(f["fecha"])), []).append(f)
    destinos = {(i["ayudante_id"], str(i["fecha"])): i for i in imputaciones}
    resultado, usados = [], set()
    for clave, grupo in grupos.items():
        nombre = nombres.get(clave[0], f"Ayudante #{clave[0]}")
        historicos = [
            g for g in gastos if g.get("categoria") == "Ayudantes"
            and g.get("proveedor") == nombre and str(g.get("fecha")) == clave[1]
            and g["tipo"] in ("faena", "presupuesto")
            and any(g["referencia_destino"] == f.get(
                "faena_id_vinculada" if g["tipo"] == "faena" else "num_presupuesto"
            ) for f in grupo)
        ]
        usados.update((g["tipo"], g["id"]) for g in historicos)
        candidatos = por_dia.get(clave) or historicos
        revision = len(candidatos) > 1
        pago = candidatos[0] if len(candidatos) == 1 else {}
        importe = None if revision else float(pago.get("importe", 50))
        pagado = None if revision else float(
            pago.get("importe_pagado") if pago.get("importe_pagado") is not None else pago.get("pagado", 0)
        )
        imputacion = destinos.get(clave)
        resultado.append({
            "id": min(f["id"] for f in grupo), "tipo": "jornada", "fecha": clave[1],
            "ayudante_id": clave[0], "proveedor": nombre, "concepto": "Jornada de ayudante",
            "categoria": "Ayudantes", "importe": importe, "importe_pagado": pagado,
            "registrado": bool(candidatos), "revision": revision,
            "pago_directo": bool(por_dia.get(clave)),
            "pendiente": None if revision else round(max(importe - pagado, 0), 2),
            "estado_pago": "Revisar" if revision else "Pagado" if importe > 0 and pagado >= importe else "Parcial" if pagado > 0 else "No pagado",
            "forma_pago": pago.get("forma_pago") or "Efectivo",
            "lugares": list(dict.fromkeys(" · ".join(str(f.get(c) or "") for c in ("cliente", "obra", "ubicacion")).strip(" ·") or "Sin lugar indicado" for f in grupo)),
            "imputacion": imputacion, "version": imputacion["version"] if imputacion else 0,
            "historicos": [(g["tipo"], g["id"]) for g in historicos],
        })
    return resultado, usados


def consultar_costes(db, postgres=False):
    consulta = ("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()"
                if postgres else "SELECT name FROM sqlite_master WHERE type='table'")
    tablas = {next(iter(f.values())) for f in filas(db, consulta)}

    def leer(*nombres):
        tabla = next((t for t in nombres if t in tablas), None)
        return filas(db, f"SELECT * FROM {tabla}") if tabla else []

    gastos = []
    for tabla, alias, tipo, referencia in (
        ("gastos_faenas_extras", "gasto_faenas", "faena", "faena_id"),
        ("gastos_presupuestos", "gasto_presupuesto", "presupuesto", "num_presupuesto"),
    ):
        gastos += [{**g, "tipo": tipo, "referencia_destino": g[referencia]} for g in leer(tabla, alias)]
    costes, usados = agrupar_costes(
        leer("fichajes_ayudantes"), leer("pagos_jornadas"), gastos,
        {a["id"]: a["nombre"] for a in leer("ayudantes")}, leer("imputaciones_ayudantes"),
    )
    return costes, usados


def destinos_costes(db):
    resultado = [{"destino": "alucarpin", "id": None, "nombre": "Alucarpin · gasto general del día"}]
    for tipo, sql in (
        ("faena", "SELECT id,cliente,obra FROM faenas ORDER BY id DESC"),
        ("presupuesto", "SELECT id,cliente,num_presupuesto FROM presupuestos ORDER BY id DESC"),
        ("propio", "SELECT id,cliente,obra FROM trabajos_propios WHERE tipo='reparacion' ORDER BY id DESC"),
    ):
        for f in filas(db, sql):
            resultado.append({"destino": tipo, "id": f["id"], "nombre": f"{tipo.title()} #{f['id']} · {f['cliente']} · {f.get('obra') or f.get('num_presupuesto') or 'Sin número'}"})
    return resultado


def guardar_imputacion(db, ayudante_id, fecha, destino, ident, version, postgres=False):
    if fecha > date.today():
        raise ValueError("No se puede imputar un día futuro.")
    if destino not in ("alucarpin", "faena", "presupuesto", "propio") or (destino == "alucarpin") != (ident is None):
        raise ValueError("Selecciona Alucarpin o una obra completa.")
    if postgres:
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", (f"coste-ayudante:{ayudante_id}:{fecha}",))
    if not filas(db, "SELECT id FROM fichajes_ayudantes WHERE ayudante_id=? AND fecha=?", (ayudante_id, fecha.isoformat())):
        raise ValueError("El ayudante no tiene ningún día registrado en esa fecha.")
    costes, _ = consultar_costes(db, postgres)
    if any(c["revision"] for c in costes if c["ayudante_id"] == ayudante_id and c["fecha"] == fecha.isoformat()):
        raise ValueError("Hay varios pagos para este ayudante y día. Revisa los pagos antes de imputar el gasto.")
    if destino != "alucarpin":
        tabla = {"faena": "faenas", "presupuesto": "presupuestos", "propio": "trabajos_propios"}[destino]
        filtro = " AND tipo='reparacion'" if destino == "propio" else ""
        if not filas(db, f"SELECT id FROM {tabla} WHERE id=?{filtro}", (ident,)):
            raise ValueError("La obra elegida ya no existe.")
    anteriores = filas(db, "SELECT * FROM imputaciones_ayudantes WHERE ayudante_id=? AND fecha=?", (ayudante_id, fecha.isoformat()))
    anterior = anteriores[0] if anteriores else None
    actual = anterior["version"] if anterior else 0
    valores = (ident if destino == "faena" else None, ident if destino == "presupuesto" else None, ident if destino == "propio" else None)
    if actual != version:
        if anterior and anterior["destino"] == destino and tuple(anterior[c] for c in ("faena_id", "presupuesto_id", "trabajo_id")) == valores and actual == version + 1:
            return anterior
        raise ValueError("El destino del gasto ha cambiado en otro dispositivo. Actualiza antes de guardar.")
    if anterior:
        db.execute("UPDATE imputaciones_ayudantes SET destino=?,faena_id=?,presupuesto_id=?,trabajo_id=?,version=version+1,actualizado_en=CURRENT_TIMESTAMP WHERE ayudante_id=? AND fecha=?",
                   (destino, *valores, ayudante_id, fecha.isoformat()))
    else:
        db.execute("INSERT INTO imputaciones_ayudantes(ayudante_id,fecha,destino,faena_id,presupuesto_id,trabajo_id) VALUES(?,?,?,?,?,?)",
                   (ayudante_id, fecha.isoformat(), destino, *valores))
    return filas(db, "SELECT * FROM imputaciones_ayudantes WHERE ayudante_id=? AND fecha=?", (ayudante_id, fecha.isoformat()))[0]


def costes_destino(db, destino, ident, postgres=False):
    costes, _ = consultar_costes(db, postgres)
    usados = {tuple(h) for c in costes if c["imputacion"] for h in c["historicos"]}
    columna = {"faena": "faena_id", "presupuesto": "presupuesto_id", "propio": "trabajo_id"}.get(destino)
    return [c for c in costes if c["imputacion"] and c["imputacion"]["destino"] == destino
            and (destino == "alucarpin" or c["imputacion"][columna] == ident)], usados
