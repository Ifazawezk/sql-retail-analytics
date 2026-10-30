-- Q24. At what time of day do people shop during Ramadan compared with the rest of the year?
-- Iftar in Doha falls at roughly 17:45 to 18:15 during the Ramadan months in
-- the data, so the late afternoon band is the hour or two before it.
WITH tagged AS (
    SELECT
        CAST(strftime('%H', o.ordered_at) AS INTEGER) AS hour,
        CASE WHEN EXISTS (
                SELECT 1 FROM calendar_events AS e
                WHERE e.kind = 'ramadan'
                  AND date(o.ordered_at) BETWEEN e.start_date AND e.end_date
             ) THEN 1 ELSE 0
        END AS in_ramadan
    FROM orders AS o
),
banded AS (
    SELECT
        CASE
            WHEN hour < 12 THEN 1
            WHEN hour < 16 THEN 2
            WHEN hour < 19 THEN 3
            WHEN hour < 22 THEN 4
            ELSE 5
        END AS band_order,
        CASE
            WHEN hour < 12 THEN 'Morning (07:00-11:59)'
            WHEN hour < 16 THEN 'Midday (12:00-15:59)'
            WHEN hour < 19 THEN 'Late afternoon (16:00-18:59)'
            WHEN hour < 22 THEN 'Evening (19:00-21:59)'
            ELSE 'Late night (22:00-23:59)'
        END AS time_band,
        in_ramadan
    FROM tagged
)
SELECT
    time_band,
    SUM(in_ramadan)                                                     AS ramadan_orders,
    ROUND(100.0 * SUM(in_ramadan) / SUM(SUM(in_ramadan)) OVER (), 1)    AS ramadan_share_pct,
    SUM(1 - in_ramadan)                                                 AS other_orders,
    ROUND(100.0 * SUM(1 - in_ramadan) / SUM(SUM(1 - in_ramadan)) OVER (), 1) AS other_share_pct
FROM banded
GROUP BY band_order, time_band
ORDER BY band_order;
