-- Q21. In each month, on which day did the 7-day rolling average of revenue peak, and what was going on?
-- The rolling window covers the day itself and the six days before it. Days
-- with no orders count as zero, so a full calendar is built first.
WITH RECURSIVE days(day) AS (
    SELECT date(MIN(ordered_at)) FROM orders
    UNION ALL
    SELECT date(day, '+1 day')
    FROM days
    WHERE day < (SELECT date(MAX(ordered_at)) FROM orders)
),
daily AS (
    SELECT date(o.ordered_at) AS day, SUM(oi.line_total) AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY date(o.ordered_at)
),
rolling AS (
    SELECT
        d.day,
        AVG(COALESCE(dl.revenue, 0)) OVER last_7 AS avg_7d,
        COUNT(*) OVER last_7                     AS days_in_window
    FROM days AS d
    LEFT JOIN daily AS dl ON dl.day = d.day
    WINDOW last_7 AS (ORDER BY d.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
),
ranked AS (
    SELECT
        day,
        avg_7d,
        ROW_NUMBER() OVER (PARTITION BY strftime('%Y-%m', day)
                           ORDER BY avg_7d DESC, day) AS position
    FROM rolling
    WHERE days_in_window = 7
)
SELECT
    strftime('%Y-%m', r.day)    AS month,
    r.day                       AS peak_day,
    ROUND(r.avg_7d, 2)          AS rolling_7d_avg_qar,
    (SELECT group_concat(e.name, ', ')
     FROM calendar_events AS e
     WHERE e.start_date <= r.day
       AND e.end_date >= date(r.day, '-6 days'))   AS events_in_window
FROM ranked AS r
WHERE r.position = 1
ORDER BY month;
