-- Q27. What is a customer worth in gross profit after 3, 6 and 12 months, by the quarter they joined?
-- Adding up lifetime spend makes new customers look poor only because they have
-- had less time, so everyone is measured over the same time since joining, and
-- a cohort gets a figure only when every member has been around that long.
-- Customers who stopped shopping stay in the average, or the figure would
-- describe the survivors. Value is gross profit after refunds, and a refunded
-- item keeps its cost because groceries that come back are usually thrown away.
WITH last_day AS (
    SELECT date(MAX(ordered_at)) AS day FROM orders
),
returned AS (
    SELECT order_item_id, SUM(refund_amount) AS refund
    FROM returns
    GROUP BY order_item_id
),
order_value AS (
    SELECT
        o.customer_id,
        date(o.ordered_at) AS day,
        SUM(oi.line_total - oi.quantity * oi.unit_cost - COALESCE(r.refund, 0)) AS value
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    LEFT JOIN returned AS r ON r.order_item_id = oi.order_item_id
    GROUP BY o.order_id, o.customer_id, date(o.ordered_at)
),
customer_value AS (
    SELECT
        c.customer_id,
        c.joined_on,
        strftime('%Y', c.joined_on) || '-Q'
            || ((CAST(strftime('%m', c.joined_on) AS INTEGER) + 2) / 3)                 AS joined_quarter,
        SUM(CASE WHEN v.day < date(c.joined_on, '+3 months') THEN v.value ELSE 0 END)   AS value_3m,
        SUM(CASE WHEN v.day < date(c.joined_on, '+6 months') THEN v.value ELSE 0 END)   AS value_6m,
        SUM(CASE WHEN v.day < date(c.joined_on, '+12 months') THEN v.value ELSE 0 END)  AS value_12m,
        COALESCE(SUM(v.value), 0)                                                       AS value_to_date,
        MAX(v.day)                                                                      AS last_order
    FROM customers AS c
    LEFT JOIN order_value AS v ON v.customer_id = c.customer_id
    GROUP BY c.customer_id, c.joined_on
),
cohorts AS (
    SELECT
        joined_quarter,
        COUNT(*)            AS customers,
        MAX(joined_on)      AS last_joined,
        SUM(value_3m)       AS value_3m,
        SUM(value_6m)       AS value_6m,
        SUM(value_12m)      AS value_12m,
        SUM(value_to_date)  AS value_to_date,
        SUM(CASE WHEN julianday((SELECT day FROM last_day)) - julianday(last_order) < 90
                 THEN 1 ELSE 0 END) AS active
    FROM customer_value
    GROUP BY joined_quarter
)
SELECT
    c.joined_quarter,
    c.customers,
    CASE WHEN date(c.last_joined, '+3 months') <= d.day
         THEN ROUND(c.value_3m / c.customers, 2) END    AS value_3m_qar,
    CASE WHEN date(c.last_joined, '+6 months') <= d.day
         THEN ROUND(c.value_6m / c.customers, 2) END    AS value_6m_qar,
    CASE WHEN date(c.last_joined, '+12 months') <= d.day
         THEN ROUND(c.value_12m / c.customers, 2) END   AS value_12m_qar,
    ROUND(c.value_to_date / c.customers, 2)             AS value_to_date_qar,
    ROUND(100.0 * c.active / c.customers, 1)            AS active_last_90_days_pct
FROM cohorts AS c
CROSS JOIN last_day AS d
ORDER BY c.joined_quarter;
