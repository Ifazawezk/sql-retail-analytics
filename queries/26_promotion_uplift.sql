-- Q26. When a product goes on its weekly promotion, how much more of it sells, and does the extra volume cover the discount?
-- There is no promotions table, so a promotion is read from the sales: a line
-- sold at 10% off marks that product as on promotion for that Monday to Sunday
-- week. A promotion week with no sales leaves no trace at all, which would
-- flatter the result, so only steady sellers are compared: products that sold
-- in at least 80% of the weeks. Weeks touching Ramadan or Eid are left out
-- because their demand and their 15% discounts are a different story. Each
-- product is compared with itself, per 100 orders, so that busy and quiet weeks
-- compare fairly, and every product counts in both columns.
WITH RECURSIVE bounds AS (
    SELECT date(MIN(ordered_at), '-6 days', 'weekday 1') AS first_week,
           date(MAX(ordered_at), '-6 days', 'weekday 1') AS last_week
    FROM orders
),
weeks(week_start) AS (
    SELECT first_week FROM bounds
    UNION ALL
    SELECT date(week_start, '+7 days')
    FROM weeks
    WHERE week_start < (SELECT last_week FROM bounds)
),
plain_weeks AS (
    SELECT w.week_start
    FROM weeks AS w
    WHERE NOT EXISTS (
        SELECT 1 FROM calendar_events AS e
        WHERE e.kind IN ('ramadan', 'eid')
          AND e.start_date <= date(w.week_start, '+6 days')
          AND e.end_date >= w.week_start
    )
),
week_orders AS (
    SELECT date(ordered_at, '-6 days', 'weekday 1') AS week_start, COUNT(*) AS orders
    FROM orders
    GROUP BY 1
),
lines AS (
    SELECT
        date(o.ordered_at, '-6 days', 'weekday 1')                          AS week_start,
        oi.product_id,
        oi.quantity,
        oi.line_total - oi.quantity * oi.unit_cost                          AS gross_profit,
        ROUND(100.0 * oi.discount_amount / (oi.quantity * oi.unit_price))   AS discount_pct
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
),
product_weeks AS (
    SELECT
        l.product_id,
        l.week_start,
        SUM(l.quantity)                                         AS units,
        SUM(l.gross_profit)                                     AS gross_profit,
        MAX(CASE WHEN l.discount_pct = 10 THEN 1 ELSE 0 END)    AS on_promotion
    FROM lines AS l
    JOIN plain_weeks AS pw ON pw.week_start = l.week_start
    GROUP BY l.product_id, l.week_start
),
steady_sellers AS (
    SELECT product_id
    FROM product_weeks
    GROUP BY product_id
    HAVING COUNT(*) >= 0.8 * (SELECT COUNT(*) FROM plain_weeks)
),
-- Every steady seller in every week, so a week with no sales counts as zero.
grid AS (
    SELECT
        s.product_id,
        w.week_start,
        wo.orders,
        COALESCE(g.units, 0)            AS units,
        COALESCE(g.gross_profit, 0)     AS gross_profit,
        COALESCE(g.on_promotion, 0)     AS on_promotion
    FROM steady_sellers AS s
    CROSS JOIN plain_weeks AS w
    JOIN week_orders AS wo ON wo.week_start = w.week_start
    LEFT JOIN product_weeks AS g
           ON g.product_id = s.product_id AND g.week_start = w.week_start
),
product_rates AS (
    SELECT
        product_id,
        SUM(on_promotion)                                                           AS promo_weeks,
        100.0 * SUM(on_promotion * units) / SUM(on_promotion * orders)              AS promo_units,
        100.0 * SUM((1 - on_promotion) * units) / SUM((1 - on_promotion) * orders)  AS normal_units,
        100.0 * SUM(on_promotion * gross_profit) / SUM(on_promotion * orders)       AS promo_profit,
        100.0 * SUM((1 - on_promotion) * gross_profit)
            / SUM((1 - on_promotion) * orders)                                      AS normal_profit
    FROM grid
    GROUP BY product_id
    HAVING SUM(on_promotion) >= 3
),
by_group AS (
    SELECT
        c.name                  AS category,
        0                       AS sort_key,
        COUNT(*)                AS products,
        SUM(r.promo_weeks)      AS promo_weeks,
        SUM(r.normal_units)     AS normal_units,
        SUM(r.promo_units)      AS promo_units,
        SUM(r.normal_profit)    AS normal_profit,
        SUM(r.promo_profit)     AS promo_profit
    FROM product_rates AS r
    JOIN products   AS p ON p.product_id = r.product_id
    JOIN categories AS c ON c.category_id = p.category_id
    GROUP BY c.name
    UNION ALL
    SELECT 'All steady sellers', 1, COUNT(*), SUM(promo_weeks), SUM(normal_units), SUM(promo_units),
           SUM(normal_profit), SUM(promo_profit)
    FROM product_rates
)
SELECT
    category,
    products,
    promo_weeks,
    ROUND(normal_units, 2)                                  AS units_per_100_orders_normal,
    ROUND(promo_units, 2)                                   AS units_per_100_orders_promo,
    ROUND(100.0 * (promo_units / normal_units - 1), 1)      AS unit_uplift_pct,
    ROUND(normal_profit, 2)                                 AS profit_per_100_orders_normal_qar,
    ROUND(promo_profit, 2)                                  AS profit_per_100_orders_promo_qar,
    ROUND(100.0 * (promo_profit / normal_profit - 1), 1)    AS profit_change_pct
FROM by_group
ORDER BY sort_key, unit_uplift_pct DESC;
