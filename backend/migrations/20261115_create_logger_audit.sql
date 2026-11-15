CREATE SEQUENCE IF NOT EXISTS public.logger_change_order_seq AS bigint;

CREATE TABLE IF NOT EXISTS public.logger (
    record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id character varying
        REFERENCES public.sessions(session_id) ON DELETE SET NULL,
    session_id_original character varying NOT NULL,
    processing_target text NOT NULL CHECK (processing_target IN ('test', 'production')),
    processing_run_id uuid NOT NULL,
    change_order bigint NOT NULL,
    table_name text NOT NULL,
    column_name text NOT NULL,
    row_key jsonb NOT NULL,
    operation text NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    value_before jsonb,
    value_after jsonb,
    created_at timestamp without time zone NOT NULL
        DEFAULT timezone('Asia/Kolkata', now()),
    rolled_back_at timestamp without time zone
);

CREATE INDEX IF NOT EXISTS logger_session_order_idx
    ON public.logger (session_id_original, processing_target, change_order);
CREATE INDEX IF NOT EXISTS logger_run_idx
    ON public.logger (processing_run_id);

ALTER TABLE public.logger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.logger FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.logger TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.logger_change_order_seq TO service_role;

CREATE OR REPLACE FUNCTION public.logger_primary_key(
    p_table oid,
    p_row jsonb
)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = pg_catalog, public
AS $function$
    SELECT COALESCE(
        jsonb_object_agg(
            attribute.attname::text,
            p_row -> attribute.attname::text
            ORDER BY key_column.ordinality
        ),
        '{}'::jsonb
    )
    FROM pg_index AS primary_index
    CROSS JOIN LATERAL
        unnest(primary_index.indkey) WITH ORDINALITY
        AS key_column(attnum, ordinality)
    JOIN pg_attribute AS attribute
      ON attribute.attrelid = primary_index.indrelid
     AND attribute.attnum = key_column.attnum
     AND NOT attribute.attisdropped
    WHERE primary_index.indrelid = p_table
      AND primary_index.indisprimary;
$function$;

CREATE OR REPLACE FUNCTION public.logger_capture_row_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    request_headers jsonb;
    processing_session character varying;
    processing_run uuid;
    processing_target_name text;
    old_row jsonb;
    new_row jsonb;
    affected_row jsonb;
    affected_row_key jsonb;
    current_column text;
    old_value jsonb;
    new_value jsonb;
    row_change_order bigint;
BEGIN
    IF current_setting('vehnicate.audit_disabled', true) = 'true' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    request_headers := COALESCE(
        NULLIF(current_setting('request.headers', true), ''),
        '{}'
    )::jsonb;
    processing_session :=
        NULLIF(request_headers ->> 'x-processing-session-id', '');
    processing_run :=
        NULLIF(request_headers ->> 'x-processing-run-id', '')::uuid;
    processing_target_name :=
        NULLIF(request_headers ->> 'x-processing-target', '');

    IF processing_session IS NULL
       OR processing_run IS NULL
       OR processing_target_name IS NULL
       OR processing_target_name NOT IN ('test', 'production') THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'INSERT' THEN
        new_row := to_jsonb(NEW);
        affected_row := new_row;
    ELSIF TG_OP = 'UPDATE' THEN
        old_row := to_jsonb(OLD);
        new_row := to_jsonb(NEW);
        affected_row := new_row;
    ELSE
        old_row := to_jsonb(OLD);
        affected_row := old_row;
    END IF;

    affected_row_key := public.logger_primary_key(TG_RELID, affected_row);
    IF affected_row_key = '{}'::jsonb THEN
        RAISE EXCEPTION 'Cannot audit %.% without a primary key',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        FOR current_column, new_value IN
            SELECT key, value FROM jsonb_each(new_row)
        LOOP
            old_value := old_row -> current_column;
            IF old_value IS DISTINCT FROM new_value THEN
                IF row_change_order IS NULL THEN
                    row_change_order := nextval(
                        'public.logger_change_order_seq'::regclass
                    );
                END IF;
                INSERT INTO public.logger (
                    session_id,
                    session_id_original,
                    processing_target,
                    processing_run_id,
                    change_order,
                    table_name,
                    column_name,
                    row_key,
                    operation,
                    value_before,
                    value_after
                )
                VALUES (
                    processing_session,
                    processing_session,
                    processing_target_name,
                    processing_run,
                    row_change_order,
                    TG_TABLE_NAME,
                    current_column,
                    affected_row_key,
                    TG_OP,
                    old_value,
                    new_value
                );
            END IF;
        END LOOP;
    ELSE
        row_change_order := nextval('public.logger_change_order_seq'::regclass);
        FOR current_column, new_value IN
            SELECT key, value FROM jsonb_each(affected_row)
        LOOP
            INSERT INTO public.logger (
                session_id,
                session_id_original,
                processing_target,
                processing_run_id,
                change_order,
                table_name,
                column_name,
                row_key,
                operation,
                value_before,
                value_after
            )
            VALUES (
                processing_session,
                processing_session,
                processing_target_name,
                processing_run,
                row_change_order,
                TG_TABLE_NAME,
                current_column,
                affected_row_key,
                TG_OP,
                CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE new_value END,
                CASE WHEN TG_OP = 'INSERT' THEN new_value ELSE NULL END
            );
        END LOOP;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$function$;

DO $block$
DECLARE
    table_record record;
    tables_without_primary_keys text;
BEGIN
    SELECT string_agg(format('%I', relation.relname), ', ' ORDER BY relation.relname)
      INTO tables_without_primary_keys
      FROM pg_class AS relation
      JOIN pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname = 'public'
       AND relation.relkind IN ('r', 'p')
       AND NOT relation.relispartition
       AND relation.relname <> 'logger'
       AND NOT EXISTS (
            SELECT 1
              FROM pg_index AS primary_index
             WHERE primary_index.indrelid = relation.oid
               AND primary_index.indisprimary
       );

    IF tables_without_primary_keys IS NOT NULL THEN
        RAISE EXCEPTION
            'Cannot enable complete row auditing; public tables lack primary keys: %',
            tables_without_primary_keys;
    END IF;

    FOR table_record IN
        SELECT relation.relname
          FROM pg_class AS relation
          JOIN pg_namespace AS namespace
            ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = 'public'
           AND relation.relkind IN ('r', 'p')
           AND NOT relation.relispartition
           AND relation.relname <> 'logger'
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS logger_capture_change ON public.%I',
            table_record.relname
        );
        EXECUTE format(
            'CREATE TRIGGER logger_capture_change '
            'AFTER INSERT OR UPDATE OR DELETE ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.logger_capture_row_change()',
            table_record.relname
        );
    END LOOP;
END;
$block$;

CREATE OR REPLACE FUNCTION public.rollback_session_processing(
    p_session_id character varying,
    p_session_end_time timestamp with time zone,
    p_processing_target text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    rollback_event record;
    relation_oid oid;
    row_predicate text;
    set_clause text;
    insert_columns text;
    insert_values text;
    statement text;
    rollback_time timestamp without time zone :=
        timezone('Asia/Kolkata', clock_timestamp());
    events_reversed bigint := 0;
BEGIN
    IF p_processing_target IS NULL
       OR p_processing_target NOT IN ('test', 'production') THEN
        RAISE EXCEPTION 'Invalid processing target: %', p_processing_target;
    END IF;

    PERFORM set_config('vehnicate.audit_disabled', 'true', true);

    UPDATE public.logger AS log_entry
       SET rolled_back_at = rollback_time
      FROM public.sessions AS session_row
     WHERE session_row.session_id = log_entry.session_id_original
       AND (session_row.end_time::timestamp with time zone, session_row.session_id)
           >= (p_session_end_time, p_session_id)
       AND log_entry.processing_target = p_processing_target
       AND log_entry.rolled_back_at IS NULL;

    FOR rollback_event IN
        SELECT
            log_entry.change_order,
            log_entry.table_name,
            log_entry.row_key,
            log_entry.operation,
            jsonb_object_agg(
                log_entry.column_name,
                log_entry.value_before
            ) AS before_values
          FROM public.logger AS log_entry
          JOIN public.sessions AS session_row
            ON session_row.session_id = log_entry.session_id_original
         WHERE (session_row.end_time::timestamp with time zone, session_row.session_id)
               >= (p_session_end_time, p_session_id)
           AND log_entry.processing_target = p_processing_target
           AND log_entry.rolled_back_at = rollback_time
         GROUP BY
            log_entry.change_order,
            log_entry.table_name,
            log_entry.row_key,
            log_entry.operation
         ORDER BY log_entry.change_order DESC
    LOOP
        relation_oid := to_regclass(
            format('public.%I', rollback_event.table_name)
        );
        IF relation_oid IS NULL OR rollback_event.table_name = 'logger' THEN
            RAISE EXCEPTION 'Cannot rollback unknown table %',
                rollback_event.table_name;
        END IF;

        SELECT string_agg(
                   format('t.%I IS NOT DISTINCT FROM k.%I', key_part, key_part),
                   ' AND ' ORDER BY key_part
               )
          INTO row_predicate
          FROM jsonb_object_keys(rollback_event.row_key) AS row_key_part(key_part);

        IF row_predicate IS NULL THEN
            RAISE EXCEPTION 'Missing row key for logger change %',
                rollback_event.change_order;
        END IF;

        IF rollback_event.operation = 'INSERT' THEN
            statement := format(
                'DELETE FROM public.%I AS t '
                'USING jsonb_populate_record(NULL::public.%I, $1) AS k '
                'WHERE %s',
                rollback_event.table_name,
                rollback_event.table_name,
                row_predicate
            );
            EXECUTE statement USING rollback_event.row_key;
        ELSIF rollback_event.operation = 'DELETE' THEN
            SELECT
                string_agg(format('%I', column_part), ', ' ORDER BY column_part),
                string_agg(format('r.%I', column_part), ', ' ORDER BY column_part)
              INTO insert_columns, insert_values
              FROM jsonb_object_keys(rollback_event.before_values)
                   AS before_column(column_part)
              JOIN pg_attribute AS attribute
                ON attribute.attrelid = relation_oid
               AND attribute.attname = column_part
               AND NOT attribute.attisdropped
               AND attribute.attgenerated = '';

            IF insert_columns IS NULL THEN
                RAISE EXCEPTION 'No restorable columns for logger change %',
                    rollback_event.change_order;
            END IF;

            statement := format(
                'INSERT INTO public.%I (%s) OVERRIDING SYSTEM VALUE '
                'SELECT %s FROM jsonb_populate_record(NULL::public.%I, $1) AS r',
                rollback_event.table_name,
                insert_columns,
                insert_values,
                rollback_event.table_name
            );
            EXECUTE statement USING rollback_event.before_values;
        ELSE
            SELECT string_agg(
                       format('%I = r.%I', column_part, column_part),
                       ', ' ORDER BY column_part
                   )
              INTO set_clause
              FROM jsonb_object_keys(rollback_event.before_values)
                   AS before_column(column_part)
              JOIN pg_attribute AS attribute
                ON attribute.attrelid = relation_oid
               AND attribute.attname = column_part
               AND NOT attribute.attisdropped
               AND attribute.attgenerated = '';

            IF set_clause IS NULL THEN
                RAISE EXCEPTION 'No restorable columns for logger change %',
                    rollback_event.change_order;
            END IF;

            statement := format(
                'UPDATE public.%I AS t '
                'SET %s '
                'FROM jsonb_populate_record(NULL::public.%I, $1) AS r, '
                'jsonb_populate_record(NULL::public.%I, $2) AS k '
                'WHERE %s',
                rollback_event.table_name,
                set_clause,
                rollback_event.table_name,
                rollback_event.table_name,
                row_predicate
            );
            EXECUTE statement
                USING rollback_event.before_values, rollback_event.row_key;
        END IF;
        events_reversed := events_reversed + 1;
    END LOOP;

    UPDATE public.logger AS log_entry
       SET session_id = log_entry.session_id_original
     WHERE log_entry.rolled_back_at = rollback_time
       AND log_entry.session_id IS NULL
       AND EXISTS (
            SELECT 1
              FROM public.sessions AS session_row
             WHERE session_row.session_id = log_entry.session_id_original
       );

    RETURN jsonb_build_object(
        'session_id', p_session_id,
        'processing_target', p_processing_target,
        'events_reversed', events_reversed,
        'rolled_back_at', rollback_time
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.logger_primary_key(oid, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.logger_capture_row_change() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.rollback_session_processing(
    character varying,
    timestamp with time zone,
    text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rollback_session_processing(
    character varying,
    timestamp with time zone,
    text
) TO service_role;

NOTIFY pgrst, 'reload schema';
