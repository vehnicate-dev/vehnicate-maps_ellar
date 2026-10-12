BEGIN;

ALTER TABLE public.imu_events
    ADD COLUMN IF NOT EXISTS az_rms double precision;

ALTER TABLE public.hexagons
    ADD COLUMN IF NOT EXISTS parameter double precision;

CREATE OR REPLACE FUNCTION public.refresh_hexagon_parameters()
RETURNS void
LANGUAGE sql
AS $function$
    WITH raw_scores AS MATERIALIZED (
        SELECT
            imu_events_id::text AS event_id,
            ((dp_og + dp) / 2.0) * gymax * stdp
                * (1.0 + GREATEST(COALESCE(az_rms, 0.0), 0.0) / 9.8) AS raw_score
        FROM public.imu_events
        WHERE dp_og IS NOT NULL
          AND dp IS NOT NULL
          AND gymax IS NOT NULL
          AND stdp IS NOT NULL
          AND ((dp_og + dp) / 2.0) * gymax * stdp
                * (1.0 + GREATEST(COALESCE(az_rms, 0.0), 0.0) / 9.8) >= 0
    ),
    transformed_scores AS (
        SELECT event_id, ln(1.0 + raw_score) AS transformed_score
        FROM raw_scores
    ),
    score_bounds AS (
        SELECT min(transformed_score) AS min_score,
               max(transformed_score) AS max_score
        FROM transformed_scores
    ),
    normalized_scores AS (
        SELECT
            transformed_scores.event_id,
            CASE
                WHEN score_bounds.max_score = score_bounds.min_score THEN 0.0
                ELSE (transformed_scores.transformed_score - score_bounds.min_score)
                    / (score_bounds.max_score - score_bounds.min_score)
            END AS parameter
        FROM transformed_scores
        CROSS JOIN score_bounds
    ),
    hexagon_scores AS (
        SELECT h.id, normalized_scores.parameter
        FROM public.hexagons AS h
        CROSS JOIN LATERAL (
            SELECT linked_events.event_id
            FROM unnest(h.event_id) WITH ORDINALITY
                AS linked_events(event_id, event_position)
            ORDER BY linked_events.event_position DESC
            LIMIT 1
        ) AS latest_event
        JOIN normalized_scores
          ON normalized_scores.event_id = latest_event.event_id::text
    )
    UPDATE public.hexagons AS h
    SET parameter = hexagon_scores.parameter
    FROM hexagon_scores
    WHERE h.id = hexagon_scores.id;
$function$;

GRANT EXECUTE ON FUNCTION public.refresh_hexagon_parameters() TO service_role;

COMMIT;
