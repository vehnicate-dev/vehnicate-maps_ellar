-- Run this setup once. It adds the ledger columns and installs a resumable
-- backfill function. Each function call processes at most 500 ledger rows.
ALTER TABLE public.ledger
    ADD COLUMN IF NOT EXISTS h3_index text,
    ADD COLUMN IF NOT EXISTS hexagon_id bigint,
    ADD COLUMN IF NOT EXISTS n integer,
    ADD COLUMN IF NOT EXISTS session_id text;

CREATE TABLE IF NOT EXISTS public.ledger_migration_progress (
    migration_name text PRIMARY KEY,
    last_ledger_id bigint
);

INSERT INTO public.ledger_migration_progress (migration_name, last_ledger_id)
VALUES ('ledger_structured_metadata_v1', NULL)
ON CONFLICT (migration_name) DO NOTHING;

CREATE OR REPLACE FUNCTION public.backfill_ledger_metadata(
    p_batch_size integer DEFAULT 500
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_last_ledger_id bigint;
    v_batch_end_id bigint;
    v_batch_size integer := GREATEST(1, LEAST(COALESCE(p_batch_size, 500), 5000));
    v_updated integer;
BEGIN
    SELECT last_ledger_id
    INTO v_last_ledger_id
    FROM public.ledger_migration_progress
    WHERE migration_name = 'ledger_structured_metadata_v1'
    FOR UPDATE;

    SELECT max(batch.ledger_id)
    INTO v_batch_end_id
    FROM (
        SELECT ledger_id
        FROM public.ledger
        WHERE v_last_ledger_id IS NULL OR ledger_id > v_last_ledger_id
        ORDER BY ledger_id
        LIMIT v_batch_size
    ) AS batch;

    IF v_batch_end_id IS NULL THEN
        RETURN 0;
    END IF;

    WITH batch AS MATERIALIZED (
        SELECT ledger_id
        FROM public.ledger
        WHERE (v_last_ledger_id IS NULL OR ledger_id > v_last_ledger_id)
          AND ledger_id <= v_batch_end_id
        ORDER BY ledger_id
    ),
    parsed AS (
        SELECT
            ledger.ledger_id,
            NULLIF(substring(ledger.comment FROM 'hex=([^|]+)'), '') AS parsed_h3_index,
            NULLIF(
                substring(ledger.comment FROM 'hexagons\.roaddefect_id=([0-9]+)'),
                ''
            )::bigint AS parsed_hexagon_id,
            NULLIF(substring(ledger.comment FROM 'n=([0-9]+)'), '')::integer AS parsed_n,
            COALESCE(
                NULLIF(substring(ledger.comment FROM 'confirmer_rank=([0-9]+)'), '')::integer,
                NULLIF(substring(ledger.comment FROM 'rD=([0-9]+)'), '')::integer,
                NULLIF(substring(ledger.comment FROM 'nd=([0-9]+)'), '')::integer
            ) AS parsed_confirmation_rank
        FROM public.ledger AS ledger
        JOIN batch USING (ledger_id)
    )
    UPDATE public.ledger AS ledger
    SET
        h3_index = COALESCE(ledger.h3_index, parsed.parsed_h3_index),
        hexagon_id = COALESCE(ledger.hexagon_id, parsed.parsed_hexagon_id),
        n = CASE
            WHEN ledger.comment LIKE 'Confirmation reward (liquid)%' THEN NULL
            ELSE COALESCE(ledger.n, parsed.parsed_n)
        END,
        session_id = COALESCE(
            ledger.session_id,
            CASE
                WHEN parsed.parsed_n IS NOT NULL THEN (
                    SELECT hex.trip_id[parsed.parsed_n]::text
                    FROM public.hexagons AS hex
                    WHERE hex.id = COALESCE(
                        parsed.parsed_hexagon_id,
                        ledger.hexagon_id
                    )
                      AND cardinality(hex.trip_id) >= parsed.parsed_n
                      AND hex.trip_id[parsed.parsed_n] IS NOT NULL
                    LIMIT 1
                )
                WHEN parsed.parsed_confirmation_rank IS NOT NULL THEN (
                    SELECT trip.session_id::text
                    FROM public.hexagons AS hex
                    CROSS JOIN LATERAL
                        unnest(hex.rd_trip_ids) WITH ORDINALITY
                        AS trip(session_id, trip_order)
                    JOIN public.sessions AS session
                      ON session.session_id = trip.session_id
                     AND session.user_id =
                         hex.nd[parsed.parsed_confirmation_rank + 1]
                    WHERE hex.id = COALESCE(
                        parsed.parsed_hexagon_id,
                        ledger.hexagon_id
                    )
                      AND parsed.parsed_confirmation_rank > 0
                      AND cardinality(hex.nd) > parsed.parsed_confirmation_rank
                    ORDER BY trip.trip_order
                    LIMIT 1
                )
            END
        ),
        comment = CASE
            WHEN ledger.comment IS NULL THEN NULL
            ELSE btrim(
                regexp_replace(
                    regexp_replace(
                        ledger.comment,
                        '\s*\|\s*(nd|rD)=([0-9]+)',
                        ' | confirmer_rank=\2',
                        'g'
                    ),
                    '\s*\|\s*(hex=[^|]*|hexagons\.roaddefect_id=[^|]*|n=[^|]*)',
                    '',
                    'g'
                ),
                ' |'
            )
        END
    FROM parsed
    WHERE ledger.ledger_id = parsed.ledger_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    UPDATE public.ledger_migration_progress
    SET last_ledger_id = v_batch_end_id
    WHERE migration_name = 'ledger_structured_metadata_v1';

    RETURN v_updated;
END;
$$;

REVOKE ALL ON FUNCTION public.backfill_ledger_metadata(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.backfill_ledger_metadata(integer) FROM anon, authenticated;

-- After setup, run this repeatedly in the SQL Editor until it returns 0:
-- SELECT public.backfill_ledger_metadata(500);
--
-- Once complete, the temporary migration objects can be removed:
-- DROP FUNCTION public.backfill_ledger_metadata(integer);
-- DROP TABLE public.ledger_migration_progress;
