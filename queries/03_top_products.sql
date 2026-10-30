-- Q03. Which 10 products bring in the most revenue, and what margin do they earn?
SELECT
    p.name                                                          AS product,
    c.name                                                          AS category,
    SUM(oi.quantity)                                                AS units_sold,
    ROUND(SUM(oi.line_total), 2)                                    AS revenue_qar,
    ROUND(100.0 * SUM(oi.line_total - oi.quantity * oi.unit_cost)
          / SUM(oi.line_total), 1)                                  AS gross_margin_pct
FROM order_items AS oi
JOIN products   AS p ON p.product_id = oi.product_id
JOIN categories AS c ON c.category_id = p.category_id
GROUP BY p.product_id, p.name, c.name
ORDER BY revenue_qar DESC
LIMIT 10;
