-- Q29. Where did delivery growth come from: more orders or bigger baskets, and customers new to delivery or existing users?
-- Compares the latest three calendar months with the same months a year before,
-- so the season matches and every branch is open in both. The revenue change
-- splits exactly into two parts. The orders effect is the extra orders at last
-- year's average order value. The basket effect is the change in average order
-- value on this year's orders. Lusail had only just opened in the earlier
-- period, so its growth starts from a low base.
WITH periods AS (
    SELECT
        date(MAX(ordered_at), 'start of month', '-14 months')   AS before_start,
        date(MAX(ordered_at), 'start of month', '-11 months')   AS before_end,
        date(MAX(ordered_at), 'start of month', '-2 months')    AS now_start,
        date(MAX(ordered_at), 'start of month', '+1 month')     AS now_end
    FROM orders
),
delivery_orders AS (
    SELECT o.order_id, o.branch_id, o.customer_id, o.ordered_at, SUM(oi.line_total) AS value
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    WHERE o.channel = 'delivery'
    GROUP BY o.order_id, o.branch_id, o.customer_id, o.ordered_at
),
first_delivery AS (
    SELECT customer_id, MIN(ordered_at) AS first_at
    FROM delivery_orders
    GROUP BY customer_id
),
labelled AS (
    SELECT
        d.branch_id,
        d.value,
        CASE WHEN d.ordered_at >= p.now_start THEN 1 ELSE 0 END     AS is_now,
        CASE WHEN f.first_at >= p.now_start THEN 1 ELSE 0 END       AS new_to_delivery
    FROM delivery_orders AS d
    CROSS JOIN periods AS p
    JOIN first_delivery AS f ON f.customer_id = d.customer_id
    WHERE (d.ordered_at >= p.before_start AND d.ordered_at < p.before_end)
       OR (d.ordered_at >= p.now_start AND d.ordered_at < p.now_end)
),
by_group AS (
    SELECT
        b.name                                      AS branch,
        0                                           AS sort_key,
        SUM(1 - l.is_now)                           AS orders_before,
        SUM(l.is_now)                               AS orders_now,
        SUM((1 - l.is_now) * l.value)               AS revenue_before,
        SUM(l.is_now * l.value)                     AS revenue_now,
        SUM(l.is_now * l.new_to_delivery * l.value) AS new_user_revenue
    FROM labelled AS l
    JOIN branches AS b ON b.branch_id = l.branch_id
    GROUP BY b.name
    UNION ALL
    SELECT 'All branches', 1, SUM(1 - is_now), SUM(is_now), SUM((1 - is_now) * value),
           SUM(is_now * value), SUM(is_now * new_to_delivery * value)
    FROM labelled
)
SELECT
    branch,
    orders_before,
    orders_now,
    ROUND(100.0 * (1.0 * orders_now / orders_before - 1), 1)            AS order_growth_pct,
    ROUND(revenue_before, 2)                                            AS revenue_before_qar,
    ROUND(revenue_now, 2)                                               AS revenue_now_qar,
    ROUND(revenue_now - revenue_before, 2)                              AS revenue_change_qar,
    ROUND((orders_now - orders_before) * revenue_before / orders_before, 2) AS orders_effect_qar,
    ROUND(orders_now * (revenue_now / orders_now - revenue_before / orders_before), 2) AS basket_effect_qar,
    ROUND(100.0 * new_user_revenue / revenue_now, 1)                    AS new_to_delivery_revenue_pct
FROM by_group
ORDER BY sort_key, revenue_change_qar DESC;
