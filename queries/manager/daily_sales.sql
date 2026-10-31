-- How did one branch trade on each day between two dates?
-- Parameters: :branch_id, :start_date and :end_date (YYYY-MM-DD, both included).
-- There is one row per day the branch was open, so a day with no orders counts
-- as zero and days before the branch opened are left out. ordered_at holds a
-- time as well as a date, so the end of the range is tested as "before the next
-- day"; BETWEEN would lose the orders placed on the last day. Returns count
-- against the day of the original order, not the day the item came back.
WITH RECURSIVE days(day) AS (
    SELECT max(:start_date, (SELECT opened_on FROM branches WHERE branch_id = :branch_id))
    UNION ALL
    SELECT date(day, '+1 day')
    FROM days
    WHERE day < :end_date
),
returned AS (
    SELECT order_item_id, SUM(quantity) AS units, SUM(refund_amount) AS refund
    FROM returns
    GROUP BY order_item_id
),
lines AS (
    SELECT
        date(o.ordered_at)              AS day,
        o.order_id,
        o.channel,
        oi.quantity,
        oi.line_total,
        oi.quantity * oi.unit_cost      AS line_cost,
        COALESCE(r.units, 0)            AS units_returned,
        COALESCE(r.refund, 0)           AS refund
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    LEFT JOIN returned AS r ON r.order_item_id = oi.order_item_id
    WHERE o.branch_id = :branch_id
      AND o.ordered_at >= :start_date
      AND o.ordered_at < date(:end_date, '+1 day')
),
daily AS (
    SELECT
        day,
        COUNT(DISTINCT order_id)                                         AS orders,
        COUNT(DISTINCT CASE WHEN channel = 'delivery' THEN order_id END) AS delivery_orders,
        SUM(quantity)                                                    AS units_sold,
        SUM(line_total)                                                  AS revenue,
        SUM(line_total) - SUM(line_cost)                                 AS gross_profit,
        SUM(units_returned)                                              AS units_returned,
        SUM(refund)                                                      AS refunds
    FROM lines
    GROUP BY day
)
SELECT
    d.day                                   AS date,
    COALESCE(s.orders, 0)                   AS orders,
    COALESCE(s.delivery_orders, 0)          AS delivery_orders,
    COALESCE(s.units_sold, 0)               AS units_sold,
    ROUND(COALESCE(s.revenue, 0), 2)        AS revenue_qar,
    ROUND(COALESCE(s.gross_profit, 0), 2)   AS gross_profit_qar,
    COALESCE(s.units_returned, 0)           AS units_returned,
    ROUND(COALESCE(s.refunds, 0), 2)        AS refunds_qar
FROM days AS d
LEFT JOIN daily AS s ON s.day = d.day
WHERE d.day <= :end_date
ORDER BY d.day;
