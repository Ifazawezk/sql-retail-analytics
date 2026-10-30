-- Q09. Which categories have the highest return rates, and why are items returned?
WITH sold AS (
    SELECT p.category_id, SUM(oi.quantity) AS units_sold
    FROM order_items AS oi
    JOIN products AS p ON p.product_id = oi.product_id
    GROUP BY p.category_id
),
returned AS (
    SELECT
        p.category_id,
        SUM(r.quantity)         AS units_returned,
        SUM(r.refund_amount)    AS refunds
    FROM returns AS r
    JOIN order_items AS oi ON oi.order_item_id = r.order_item_id
    JOIN products    AS p  ON p.product_id = oi.product_id
    GROUP BY p.category_id
),
reasons AS (
    SELECT
        p.category_id,
        r.reason,
        ROW_NUMBER() OVER (PARTITION BY p.category_id
                           ORDER BY COUNT(*) DESC, r.reason) AS reason_rank
    FROM returns AS r
    JOIN order_items AS oi ON oi.order_item_id = r.order_item_id
    JOIN products    AS p  ON p.product_id = oi.product_id
    GROUP BY p.category_id, r.reason
)
SELECT
    c.name                                                          AS category,
    s.units_sold,
    COALESCE(rt.units_returned, 0)                                  AS units_returned,
    ROUND(100.0 * COALESCE(rt.units_returned, 0) / s.units_sold, 2) AS return_rate_pct,
    ROUND(COALESCE(rt.refunds, 0), 2)                               AS refunds_qar,
    rs.reason                                                       AS top_reason
FROM categories AS c
JOIN sold          AS s  ON s.category_id = c.category_id
LEFT JOIN returned AS rt ON rt.category_id = c.category_id
LEFT JOIN reasons  AS rs ON rs.category_id = c.category_id AND rs.reason_rank = 1
ORDER BY return_rate_pct DESC;
