"""Resumen de lectura: costes por fecha y cobros realmente registrados."""

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def periodo_actual(hoy):
    return hoy.replace(day=1), hoy.replace(day=monthrange(hoy.year, hoy.month)[1])


def calcular_resumen(db, desde, hasta, hoy, postgres=False):
    if desde > hasta:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    consulta = ("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
                if postgres else "SELECT name FROM sqlite_master WHERE type='table'")
    tablas = {next(iter(fila.values())) if hasattr(fila, "values") else fila[0]
              for fila in db.execute(consulta).fetchall()}
    avisos = []

    def leer(*nombres):
        tabla = next((nombre for nombre in nombres if nombre in tablas), None)
        if tabla is None:
            avisos.append(f"No existe {nombres[0]}; sus datos no estan disponibles.")
            return []
        cursor = db.execute(f"SELECT * FROM {tabla}")
        columnas = [columna[0] for columna in cursor.description]
        return [dict(fila) if hasattr(fila, "keys") else dict(zip(columnas, fila))
                for fila in cursor.fetchall()]

    def fecha(valor):
        if not valor:
            return None
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        try:
            return date.fromisoformat(str(valor))
        except ValueError:
            avisos.append(f"Fecha no valida: {valor}. Excluida del periodo.")
            return None

    def dinero(valor):
        try:
            numero = Decimal(str(valor if valor is not None else 0))
        except InvalidOperation as error:
            raise ValueError("Hay un importe no numerico. Revisa los datos.") from error
        if not numero.is_finite():
            raise ValueError("Hay un importe no finito. Revisa los datos.")
        return numero

    cobros = []
    totales_cobrados = {}
    for tabla, tipo, referencia in (
        ("pagos_faenas", "faena", "faena_id"),
        ("pagos_ingresos", "presupuesto", "num_presupuesto"),
    ):
        for fila in leer(tabla):
            importe = dinero(fila.get("importe_iva")) + dinero(fila.get("importe_b"))
            dia = fecha(fila.get("fecha"))
            if not dia:
                avisos.append(f"{tabla} #{fila['id']}: cobro sin fecha, fuera del periodo.")
            if dia is None or dia <= hoy:
                clave = (tipo, fila[referencia])
                totales_cobrados[clave] = totales_cobrados.get(clave, Decimal(0)) + importe
            cobros.append((dia, importe))

    pendientes_cobro = []
    sin_importe = 0

    def obra(tipo, fila, importe, cobrado, cerrado=False):
        nonlocal sin_importe
        dia = fecha(fila.get("fecha", fila.get("fecha_inicio")))
        if dia is None:
            avisos.append(f"{tipo} #{fila['id']}: sin fecha de trabajo, incluido en pendientes.")
        if dia and dia > hoy:
            return
        pendiente = max(importe - cobrado, Decimal(0)) if not cerrado else Decimal(0)
        etiqueta = fila.get("obra") or f"Presupuesto {fila.get('num_presupuesto') or fila['id']}"
        if importe <= 0 and not cerrado:
            sin_importe += 1
            avisos.append(f"{tipo} #{fila['id']}: sin importe de cobro.")
        if pendiente:
            pendientes_cobro.append({
                "tipo": tipo, "referencia": fila["id"], "cliente": fila.get("cliente") or "Sin cliente",
                "concepto": etiqueta, "fecha": dia.isoformat() if dia else None,
                "pendiente": float(pendiente),
            })

    faenas = leer("faenas")
    presupuestos = leer("presupuestos")
    for fila in faenas:
        obra("faena", fila, dinero(fila.get("precio")),
             totales_cobrados.get(("faena", fila["id"]), Decimal(0)))
    numeros = {}
    for fila in presupuestos:
        if str(fila.get("estado") or "").strip().upper() not in ("ACEPTADO", "COMPLETADO"):
            continue
        numero = fila.get("num_presupuesto")
        numeros.setdefault(numero, []).append(fila)
    for numero, filas in numeros.items():
        if len(filas) > 1 or not numero:
            avisos.append(f"Presupuesto {numero or 'sin numero'}: referencia ambigua, excluida de pendientes.")
            continue
        fila = filas[0]
        obra("presupuesto", fila, dinero(fila.get("presupuesto_final")),
             totales_cobrados.get(("presupuesto", numero), Decimal(0)),
             str(fila.get("estado") or "").strip().upper() == "COMPLETADO")
    for fila in leer("trabajos_propios"):
        if fila.get("num_presupuesto") and fila["num_presupuesto"] in numeros:
            continue
        importe = dinero(fila.get("importe"))
        pagado = fila.get("estado_cobro") == "Cobrado"
        obra("propio", fila, importe, importe if pagado else Decimal(0))
        if pagado:
            dia = fecha(fila.get("fecha_cobro"))
            if dia is None:
                avisos.append(f"Trabajo #{fila['id']}: cobrado sin fecha, fuera del periodo.")
            cobros.append((dia, importe))

    gastos = []
    for nombres, tipo, referencia in (
        (("gastos_faenas_extras", "gasto_faenas"), "faena", "faena_id"),
        (("gastos_presupuestos", "gasto_presupuesto"), "presupuesto", "num_presupuesto"),
    ):
        for fila in leer(*nombres):
            gastos.append({**fila, "tipo": tipo, "referencia_destino": fila[referencia],
                           "registrado": True, "revision": False})
    grupos = {}
    fichajes = leer("fichajes_ayudantes")
    por_id = {fila["id"]: fila for fila in fichajes}
    nombres = {fila["id"]: fila["nombre"] for fila in leer("ayudantes")}
    pagos = {}
    for pago in leer("pagos_jornadas"):
        fichaje = por_id.get(pago["fichaje_id"])
        if not fichaje:
            avisos.append(f"Pago de jornada #{pago['fichaje_id']}: fichaje inexistente.")
            continue
        pagos.setdefault((fichaje["ayudante_id"], str(fichaje["fecha"])), []).append(pago)
    for fila in fichajes:
        grupos.setdefault((fila["ayudante_id"], str(fila["fecha"])), []).append(fila)
    usados = set()
    for clave, filas in grupos.items():
        nombre = nombres.get(clave[0])
        historicos = [g for g in gastos if g.get("categoria") == "Ayudantes"
                      and g.get("proveedor") == nombre and str(g.get("fecha")) == clave[1]
                      and any(g["referencia_destino"] == f.get(
                          "faena_id_vinculada" if g["tipo"] == "faena" else "num_presupuesto")
                              for f in filas)]
        usados.update((g["tipo"], g["id"]) for g in historicos)
        candidatos = pagos.get(clave) or historicos
        revision = len(candidatos) > 1
        if revision:
            avisos.append(f"{nombre or clave[0]} | {clave[1]}: varios pagos de jornada, excluidos.")
        pago = candidatos[0] if len(candidatos) == 1 else {}
        gastos.append({
            "id": min(f["id"] for f in filas), "tipo": "jornada", "fecha": clave[1],
            "proveedor": nombre or f"Ayudante #{clave[0]}", "concepto": "Jornada de ayudante",
            "importe": pago.get("importe", 50),
            "importe_pagado": pago.get("importe_pagado") if pago.get("importe_pagado") is not None
            else pago.get("pagado", 0),
            "registrado": bool(candidatos), "revision": revision,
        })
    gastos = [g for g in gastos if (g["tipo"], g["id"]) not in usados]

    periodo = dict(cobros_recibidos=Decimal(0), gastos_registrados=Decimal(0),
                   abonado_gastos=Decimal(0), pendiente_gastos=Decimal(0),
                   jornadas_estimadas=0, coste_estimado=Decimal(0))
    for dia, importe in cobros:
        if dia and desde <= dia <= hasta and dia <= hoy:
            periodo["cobros_recibidos"] += importe
    pendientes_pago = []
    revision = 0
    estimado_pendiente = Decimal(0)
    for gasto in gastos:
        dia = fecha(gasto.get("fecha"))
        if not dia:
            avisos.append(f"Gasto {gasto['tipo']} #{gasto['id']}: sin fecha, fuera del periodo.")
        if dia and dia > hoy:
            continue
        if gasto["revision"]:
            revision += 1
            continue
        importe = dinero(gasto.get("importe"))
        pagado = dinero(gasto.get("importe_pagado") if gasto.get("importe_pagado") is not None
                        else gasto.get("pagado"))
        pendiente = max(importe - pagado, Decimal(0))
        if pendiente:
            pendientes_pago.append({
                "tipo": gasto["tipo"], "referencia": gasto["id"],
                "proveedor": gasto.get("proveedor") or "Sin proveedor",
                "concepto": gasto.get("concepto") or "Sin concepto",
                "fecha": dia.isoformat() if dia else None, "pendiente": float(pendiente),
                "estimado": not gasto["registrado"],
            })
            if not gasto["registrado"]:
                estimado_pendiente += pendiente
        if dia and desde <= dia <= hasta:
            if gasto["registrado"]:
                periodo["gastos_registrados"] += importe
                periodo["abonado_gastos"] += pagado
                periodo["pendiente_gastos"] += pendiente
            else:
                periodo["jornadas_estimadas"] += 1
                periodo["coste_estimado"] += importe
    orden = lambda fila: (fila["fecha"] or "", fila["tipo"], fila["referencia"])
    return {
        "desde": desde.isoformat(), "hasta": hasta.isoformat(), "fecha": hoy.isoformat(),
        "periodo": {k: float(v.quantize(Decimal(".01"))) if isinstance(v, Decimal) else v
                    for k, v in periodo.items()},
        "acumulado": {
            "cobros_pendientes": round(sum(f["pendiente"] for f in pendientes_cobro), 2),
            "pagos_pendientes": round(sum(f["pendiente"] for f in pendientes_pago if not f["estimado"]), 2),
            "jornadas_estimadas": sum(f["estimado"] for f in pendientes_pago),
            "coste_estimado": float(estimado_pendiente),
            "cobros_sin_importe": sin_importe,
        },
        "cobros": sorted(pendientes_cobro, key=orden),
        "pagos": sorted(pendientes_pago, key=orden),
        "revision": revision, "avisos": list(dict.fromkeys(avisos)),
    }
