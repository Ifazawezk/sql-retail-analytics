-- Q10. How much busier is an average day in Ramadan than the rest of the year?
WITH RECURSIVE days(day) AS (
    SELECT date(MIN(ordered_at)) FROM orders
    UNION ALL
    SELECT date(day, '+1 day')
    FROM days
    WHERE day < (SELECT date(MAX(ordered_at)) FROM orders)
),
daily AS (
    SELECT
        date(o.ordered_at)          AS day,
        COUNT(DISTINCT o.order_id)  AS orders,
        SUM(oi.line_total)          AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY date(o.ordered_at)
),
labelled AS (
    SELECT
        strftime('%Y', d.day) AS year,
        CASE WHEN EXISTS (
                SELECT 1 FROM calendar_events AS e
                WHERE e.kind = 'ramadan' AND d.day BETWEEN e.start_date AND e.end_date
             ) THEN 'Ramadan' ELSE 'Rest of year'
        END                             AS period,
        COALESCE(dl.orders, 0)          AS orders,
        COALESCE(dl.revenue, 0)         AS revenue
    FROM days AS d
    LEFT JOIN daily AS dl ON dl.day = d.day
),
summary AS (
    SELECT
        year,
        period,
        COUNT(*)                        AS days,
        AVG(orders)                     AS avg_orders,
        AVG(revenue)                    AS avg_revenue,
        SUM(revenue) / SUM(orders)      AS avg_order_value
    FROM labelled
    GROUP BY year, period
)
SELECT
    year,
    period,
    days,
    ROUND(avg_orders, 1)                AS avg_daily_orders,
    ROUND(avg_revenue, 2)               AS avg_daily_revenue_qar,
    ROUND(avg_order_value, 2)           AS avg_order_value_qar,
    ROUND(100.0 * (avg_revenue / MAX(CASE WHEN period = 'Rest of year' THEN avg_revenue END)
                                 OVER (PARTITION BY year) - 1), 1) AS revenue_uplift_pct
FROM summary
ORDER BY year, period;
