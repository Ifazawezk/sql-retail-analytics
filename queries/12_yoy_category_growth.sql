-- Q12. Which categories grew the most in 2025 compared with 2024?
WITH yearly AS (
    SELECT
        c.name                                                                  AS category,
        SUM(CASE WHEN strftime('%Y', o.ordered_at) = '2024' THEN oi.line_total ELSE 0 END) AS revenue_2024,
        SUM(CASE WHEN strftime('%Y', o.ordered_at) = '2025' THEN oi.line_total ELSE 0 END) AS revenue_2025
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    JOIN products    AS p  ON p.product_id = oi.product_id
    JOIN categories  AS c  ON c.category_id = p.category_id
    GROUP BY c.category_id, c.name
)
SELECT
    category,
    ROUND(revenue_2024, 2)                                          AS revenue_2024_qar,
    ROUND(revenue_2025, 2)                                          AS revenue_2025_qar,
    ROUND(revenue_2025 - revenue_2024, 2)                           AS change_qar,
    ROUND(100.0 * (revenue_2025 - revenue_2024) / revenue_2024, 1)  AS yoy_growth_pct
FROM yearly
ORDER BY yoy_growth_pct DESC;
