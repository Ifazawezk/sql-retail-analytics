-- Q02. How do the branches compare on orders, customers, revenue and gross margin?
WITH branch_lines AS (
    SELECT
        o.branch_id,
        o.order_id,
        o.customer_id,
        oi.line_total,
        oi.quantity * oi.unit_cost AS line_cost
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
)
SELECT
    b.name                                                              AS branch,
    b.opened_on,
    COUNT(DISTINCT bl.order_id)                                         AS orders,
    COUNT(DISTINCT bl.customer_id)                                      AS customers,
    ROUND(SUM(bl.line_total), 2)                                        AS revenue_qar,
    ROUND(100.0 * SUM(bl.line_total) / SUM(SUM(bl.line_total)) OVER (), 1) AS revenue_share_pct,
    ROUND(100.0 * (SUM(bl.line_total) - SUM(bl.line_cost))
          / SUM(bl.line_total), 1)                                      AS gross_margin_pct
FROM branches AS b
JOIN branch_lines AS bl ON bl.branch_id = b.branch_id
GROUP BY b.branch_id, b.name, b.opened_on
ORDER BY revenue_qar DESC;
