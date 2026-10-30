-- Q04. What share of revenue and gross profit does each category contribute?
WITH category_totals AS (
    SELECT
        c.name                                          AS category,
        SUM(oi.quantity)                                AS units_sold,
        SUM(oi.line_total)                              AS revenue,
        SUM(oi.line_total - oi.quantity * oi.unit_cost) AS gross_profit
    FROM order_items AS oi
    JOIN products   AS p ON p.product_id = oi.product_id
    JOIN categories AS c ON c.category_id = p.category_id
    GROUP BY c.category_id, c.name
)
SELECT
    category,
    units_sold,
    ROUND(revenue, 2)                                           AS revenue_qar,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 1)            AS revenue_share_pct,
    ROUND(100.0 * gross_profit / SUM(gross_profit) OVER (), 1)  AS profit_share_pct,
    ROUND(100.0 * gross_profit / revenue, 1)                    AS gross_margin_pct
FROM category_totals
ORDER BY revenue DESC;
