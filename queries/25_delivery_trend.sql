-- Q25. How fast is delivery growing as a share of orders and revenue, quarter by quarter?
WITH order_values AS (
    SELECT
        o.order_id,
        o.channel,
        strftime('%Y', o.ordered_at) || '-Q'
            || ((CAST(strftime('%m', o.ordered_at) AS INTEGER) + 2) / 3)   AS quarter,
        SUM(oi.line_total)                                                  AS order_value
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY o.order_id, o.channel, o.ordered_at
),
quarterly AS (
    SELECT
        quarter,
        COUNT(*)                                                        AS orders,
        SUM(CASE WHEN channel = 'delivery' THEN 1 ELSE 0 END)           AS delivery_orders,
        SUM(order_value)                                                AS revenue,
        SUM(CASE WHEN channel = 'delivery' THEN order_value ELSE 0 END) AS delivery_revenue
    FROM order_values
    GROUP BY quarter
)
SELECT
    quarter,
    orders,
    delivery_orders,
    ROUND(100.0 * delivery_orders / orders, 1)                          AS delivery_order_share_pct,
    ROUND(100.0 * delivery_revenue / revenue, 1)                        AS delivery_revenue_share_pct,
    ROUND(100.0 * delivery_orders / orders
          - LAG(100.0 * delivery_orders / orders) OVER (ORDER BY quarter), 1) AS share_change_pts
FROM quarterly
ORDER BY quarter;
