-- Q16. Who are the 10 most valuable customers, and how often do they shop?
WITH customer_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        date(o.ordered_at)  AS order_date,
        SUM(oi.line_total)  AS order_value
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY o.order_id, o.customer_id, o.ordered_at
)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name                          AS customer,
    b.name                                                      AS home_branch,
    COUNT(*)                                                    AS orders,
    ROUND(SUM(co.order_value), 2)                               AS lifetime_spend_qar,
    ROUND(AVG(co.order_value), 2)                               AS avg_order_value_qar,
    MIN(co.order_date)                                          AS first_order,
    MAX(co.order_date)                                          AS last_order,
    ROUND((julianday(MAX(co.order_date)) - julianday(MIN(co.order_date)))
          / NULLIF(COUNT(*) - 1, 0), 1)                         AS avg_days_between_orders
FROM customer_orders AS co
JOIN customers AS c ON c.customer_id = co.customer_id
JOIN branches  AS b ON b.branch_id = c.home_branch_id
GROUP BY c.customer_id, c.first_name, c.last_name, b.name
ORDER BY lifetime_spend_qar DESC
LIMIT 10;
