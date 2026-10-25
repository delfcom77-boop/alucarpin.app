from decimal import Decimal, InvalidOperation


def importe_acordado(texto):
    texto = texto.strip()
    if not texto:
        return None
    try:
        importe = Decimal(texto.replace(",", "."))
    except InvalidOperation as error:
        raise ValueError("Introduce un total acordado valido, sin separador de miles.") from error
    if not importe.is_finite() or importe < 0 or importe > Decimal("999999999.99"):
        raise ValueError("El total acordado debe estar entre 0 y 999999999,99 euros.")
    if importe != importe.quantize(Decimal("0.01")):
        raise ValueError("El total acordado admite como maximo dos decimales.")
    return float(importe)


def inicializar_importes(db, postgres=False):
    if postgres:
        db.execute(
            "ALTER TABLE faenas ADD COLUMN IF NOT EXISTS importe_acordado "
            "DOUBLE PRECISION CHECK (importe_acordado >= 0)"
        )
    else:
        columnas = {fila[1] for fila in db.execute("PRAGMA table_info(faenas)")}
        if columnas and "importe_acordado" not in columnas:
            db.execute(
                "ALTER TABLE faenas ADD COLUMN importe_acordado REAL "
                "CHECK (importe_acordado >= 0)"
            )


def importe_faena_sql(alias="f"):
    return (
        f"COALESCE({alias}.importe_acordado,"
        f"(SELECT SUM(j.importe) FROM jornadas_faenas j WHERE j.faena_id={alias}.id),"
        f"{alias}.precio,0)"
    )


def inicializar_beneficiarios(db, postgres=False):
    if postgres:
        db.execute(
            "ALTER TABLE pagos_faenas ADD COLUMN IF NOT EXISTS beneficiario "
            "TEXT NOT NULL DEFAULT ''"
        )
    else:
        columnas = {fila[1] for fila in db.execute("PRAGMA table_info(pagos_faenas)")}
        if columnas and "beneficiario" not in columnas:
            db.execute("ALTER TABLE pagos_faenas ADD COLUMN beneficiario TEXT NOT NULL DEFAULT ''")


def parte_terceros_sql(alias="f"):
    return (
        "(SELECT COALESCE(SUM(COALESCE(pt.importe_iva,0)+COALESCE(pt.importe_b,0)),0) "
        f"FROM pagos_faenas pt WHERE pt.faena_id={alias}.id AND TRIM(pt.beneficiario)<> '')"
    )
