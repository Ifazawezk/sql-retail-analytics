-- Q01. What are the monthly revenue, order count and average order value?
-- Revenue in every query is the sum of order line totals in QAR, after
-- promotional discounts and before any returns.
SELECT
    strftime('%Y-%m', o.ordered_at)                             AS month,
    COUNT(DISTINCT o.order_id)                                  AS orders,
    ROUND(SUM(oi.line_total), 2)                                AS revenue_qar,
    ROUND(SUM(oi.line_total) / COUNT(DISTINCT o.order_id), 2)   AS avg_order_value_qar
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
GROUP BY month
ORDER BY month;
