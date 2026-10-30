-- Q07. How do in-store and delivery baskets differ in size and value?
WITH baskets AS (
    SELECT
        o.order_id,
        o.channel,
        COUNT(*)            AS lines,
        SUM(oi.quantity)    AS units,
        SUM(oi.line_total)  AS order_value
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY o.order_id, o.channel
)
SELECT
    channel,
    COUNT(*)                        AS orders,
    ROUND(AVG(lines), 2)            AS avg_lines,
    ROUND(AVG(units), 2)            AS avg_units,
    ROUND(AVG(order_value), 2)      AS avg_order_value_qar,
    ROUND(MAX(order_value), 2)      AS largest_order_qar
FROM baskets
GROUP BY channel
ORDER BY orders DESC;
