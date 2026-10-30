-- Q22. Which regular customers are overdue for a visit, judged against their own usual gap between orders?
-- Regular means at least five orders. Overdue means the time since the last
-- order is more than three times the customer's average gap and at least 30
-- days. These are the people a win-back offer should go to first.
WITH as_of AS (
    SELECT date(MAX(ordered_at)) AS day FROM orders
),
order_gaps AS (
    SELECT
        customer_id,
        date(ordered_at) AS order_date,
        julianday(date(ordered_at))
            - julianday(date(LAG(ordered_at) OVER (PARTITION BY customer_id
                                                   ORDER BY ordered_at))) AS gap_days
    FROM orders
),
regulars AS (
    SELECT
        customer_id,
        COUNT(*)            AS orders,
        AVG(gap_days)       AS avg_gap_days,
        MAX(order_date)     AS last_order
    FROM order_gaps
    GROUP BY customer_id
    HAVING COUNT(*) >= 5
),
spend AS (
    SELECT o.customer_id, SUM(oi.line_total) AS lifetime_spend
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name                          AS customer,
    b.name                                                      AS home_branch,
    r.orders,
    ROUND(r.avg_gap_days, 1)                                    AS avg_gap_days,
    r.last_order,
    CAST(julianday(a.day) - julianday(r.last_order) AS INTEGER) AS days_since_last_order,
    ROUND(s.lifetime_spend, 2)                                  AS lifetime_spend_qar
FROM regulars AS r
CROSS JOIN as_of AS a
JOIN customers AS c ON c.customer_id = r.customer_id
JOIN branches  AS b ON b.branch_id = c.home_branch_id
JOIN spend     AS s ON s.customer_id = r.customer_id
WHERE julianday(a.day) - julianday(r.last_order) > 3 * r.avg_gap_days
  AND julianday(a.day) - julianday(r.last_order) >= 30
ORDER BY lifetime_spend_qar DESC
LIMIT 15;
