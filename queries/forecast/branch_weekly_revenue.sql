-- How much did each branch sell in each full Monday to Sunday week?
-- A week counts only if the branch was open and the data covers all seven days,
-- so the days at the very end of the data and a branch's part-week of opening
-- are left out rather than read as a slump. A full week with no orders is a
-- real zero and stays in.
WITH RECURSIVE bounds AS (
    SELECT date(MIN(ordered_at)) AS first_day, date(MAX(ordered_at)) AS last_day
    FROM orders
),
weeks(week_start) AS (
    SELECT date(first_day, '-6 days', 'weekday 1') FROM bounds
    UNION ALL
    SELECT date(week_start, '+7 days')
    FROM weeks
    WHERE date(week_start, '+7 days') <= (SELECT last_day FROM bounds)
),
branch_weeks AS (
    SELECT b.branch_id, b.name, w.week_start
    FROM branches AS b
    CROSS JOIN weeks AS w
    CROSS JOIN bounds AS d
    WHERE w.week_start >= b.opened_on
      AND w.week_start >= d.first_day
      AND date(w.week_start, '+6 days') <= d.last_day
),
sales AS (
    SELECT
        o.branch_id,
        date(o.ordered_at, '-6 days', 'weekday 1')  AS week_start,
        COUNT(DISTINCT o.order_id)                  AS orders,
        SUM(oi.line_total)                          AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY o.branch_id, date(o.ordered_at, '-6 days', 'weekday 1')
)
SELECT
    bw.name                             AS branch,
    bw.week_start,
    COALESCE(s.orders, 0)               AS orders,
    ROUND(COALESCE(s.revenue, 0), 2)    AS revenue_qar
FROM branch_weeks AS bw
LEFT JOIN sales AS s
       ON s.branch_id = bw.branch_id AND s.week_start = bw.week_start
ORDER BY bw.name, bw.week_start;
