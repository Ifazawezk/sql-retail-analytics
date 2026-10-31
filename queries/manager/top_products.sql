-- Which products brought in the most revenue at one branch between two dates?
-- Parameters: :branch_id, :start_date and :end_date (YYYY-MM-DD, both included).
SELECT
    p.name                                                  AS product,
    c.name                                                  AS category,
    SUM(oi.quantity)                                        AS units_sold,
    ROUND(SUM(oi.line_total), 2)                            AS revenue_qar,
    ROUND(100.0 * (SUM(oi.line_total) - SUM(oi.quantity * oi.unit_cost))
          / SUM(oi.line_total), 1)                          AS gross_margin_pct
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN products    AS p  ON p.product_id = oi.product_id
JOIN categories  AS c  ON c.category_id = p.category_id
WHERE o.branch_id = :branch_id
  AND o.ordered_at >= :start_date
  AND o.ordered_at < date(:end_date, '+1 day')
GROUP BY p.product_id, p.name, c.name
ORDER BY revenue_qar DESC, product
LIMIT 10;
