-- Limpieza de datos de prueba.
-- CONSERVA: ayudantes, usuarios y fichajes_ayudantes de la app.
-- Ejecutar solo despues de revisar que los datos de Supabase son de prueba.

BEGIN;

DO $$
DECLARE
    tabla TEXT;
BEGIN
    FOREACH tabla IN ARRAY ARRAY[
        'pagos_gastos',
        'pagos_faenas',
        'pagos_ingresos',
        'gastos_faenas_extras',
        'gasto_faenas',
        'gastos_presupuestos',
        'gasto_presupuesto',
        'liquidaciones'
    ] LOOP
        IF to_regclass('public.' || tabla) IS NOT NULL THEN
            EXECUTE format('DELETE FROM public.%I', tabla);
        END IF;
    END LOOP;

    IF to_regclass('public.fichajes_ayudantes') IS NOT NULL THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'fichajes_ayudantes'
              AND column_name = 'num_presupuesto'
        ) THEN
            EXECUTE 'UPDATE public.fichajes_ayudantes SET num_presupuesto = NULL';
        END IF;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'fichajes_ayudantes'
              AND column_name = 'faena_id_vinculada'
        ) THEN
            EXECUTE 'UPDATE public.fichajes_ayudantes SET faena_id_vinculada = NULL';
        END IF;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'fichajes_ayudantes'
              AND column_name = 'estado_procesamiento'
        ) THEN
            EXECUTE 'UPDATE public.fichajes_ayudantes SET estado_procesamiento = ''Pendiente''';
        END IF;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'fichajes_ayudantes'
              AND column_name = 'gasto_id'
        ) THEN
            EXECUTE 'UPDATE public.fichajes_ayudantes SET gasto_id = NULL';
        END IF;
    END IF;

    IF to_regclass('public.faenas') IS NOT NULL THEN
        EXECUTE 'DELETE FROM public.faenas';
    END IF;
    IF to_regclass('public.presupuestos') IS NOT NULL THEN
        EXECUTE 'DELETE FROM public.presupuestos';
    END IF;
END $$;

COMMIT;
