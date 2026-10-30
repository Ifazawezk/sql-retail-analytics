-- Q19. Which pairs of products are bought together far more often than chance would suggest?
-- support    = share of all orders that contain both products
-- confidence = share of orders with product A that also contain product B
-- lift       = how many times more often the pair appears than if the two
--              products were bought independently (1.0 means no link)
-- Pairs seen in fewer than 15 orders are ignored to keep the noise out.
WITH order_count AS (
    SELECT COUNT(*) AS n FROM orders
),
product_orders AS (
    SELECT product_id, COUNT(*) AS orders
    FROM order_items
    GROUP BY product_id
),
pairs AS (
    SELECT
        a.product_id    AS product_a,
        b.product_id    AS product_b,
        COUNT(*)        AS together
    FROM order_items AS a
    JOIN order_items AS b
      ON b.order_id = a.order_id
     AND b.product_id > a.product_id
    GROUP BY a.product_id, b.product_id
    HAVING COUNT(*) >= 15
)
SELECT
    pa.name                                                         AS product_a,
    pb.name                                                         AS product_b,
    p.together                                                      AS orders_together,
    ROUND(100.0 * p.together / oc.n, 2)                             AS support_pct,
    ROUND(1.0 * p.together / oa.orders, 3)                          AS confidence_a_to_b,
    ROUND(1.0 * p.together * oc.n / (oa.orders * ob.orders), 2)     AS lift
FROM pairs AS p
CROSS JOIN order_count AS oc
JOIN product_orders AS oa ON oa.product_id = p.product_a
JOIN product_orders AS ob ON ob.product_id = p.product_b
JOIN products       AS pa ON pa.product_id = p.product_a
JOIN products       AS pb ON pb.product_id = p.product_b
ORDER BY lift DESC, orders_together DESC
LIMIT 15;
