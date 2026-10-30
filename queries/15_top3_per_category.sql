-- Q15. What are the three best-selling products by units in each category?
WITH product_sales AS (
    SELECT
        p.category_id,
        p.name              AS product,
        SUM(oi.quantity)    AS units,
        SUM(oi.line_total)  AS revenue
    FROM order_items AS oi
    JOIN products AS p ON p.product_id = oi.product_id
    GROUP BY p.product_id, p.category_id, p.name
),
ranked AS (
    SELECT
        c.name                                                      AS category,
        ps.product,
        ps.units,
        ps.revenue,
        ROW_NUMBER() OVER (PARTITION BY ps.category_id
                           ORDER BY ps.units DESC, ps.revenue DESC) AS rank_in_category,
        100.0 * ps.units / SUM(ps.units) OVER (PARTITION BY ps.category_id) AS unit_share
    FROM product_sales AS ps
    JOIN categories AS c ON c.category_id = ps.category_id
)
SELECT
    category,
    rank_in_category,
    product,
    units                   AS units_sold,
    ROUND(revenue, 2)       AS revenue_qar,
    ROUND(unit_share, 1)    AS category_unit_share_pct
FROM ranked
WHERE rank_in_category <= 3
ORDER BY category, rank_in_category;
