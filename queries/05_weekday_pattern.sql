-- Q05. Which days of the week bring in the most revenue on an average day?
-- Friday and Saturday are the weekend in Qatar. A calendar of every date is
-- built first so that days without any orders still count in the average.
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
)
SELECT
    CASE strftime('%w', d.day)
        WHEN '0' THEN 'Sunday'    WHEN '1' THEN 'Monday'   WHEN '2' THEN 'Tuesday'
        WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday'
        ELSE 'Saturday'
    END                                         AS weekday,
    COUNT(*)                                    AS days,
    ROUND(AVG(COALESCE(dl.orders, 0)), 1)       AS avg_orders,
    ROUND(AVG(COALESCE(dl.revenue, 0)), 2)      AS avg_revenue_qar
FROM days AS d
LEFT JOIN daily AS dl ON dl.day = d.day
GROUP BY strftime('%w', d.day)
ORDER BY avg_revenue_qar DESC;
