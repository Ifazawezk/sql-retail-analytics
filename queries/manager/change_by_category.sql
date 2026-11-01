-- Which categories moved a branch's revenue between two periods, and which product moved each one most?
-- Parameters: :branch_id, :previous_start, :start_date and :end_date (YYYY-MM-DD).
-- The earlier period runs from :previous_start to the day before :start_date, and
-- the current one from :start_date to :end_date, both included. A product sold in
-- only one of the periods still counts, so the rows add up to the whole change in
-- revenue. The main product is the one that moved furthest the same way as its
-- category: a product that rose inside a falling category does not explain the fall.
WITH product_change AS (
    SELECT
        p.category_id,
        p.name                                                                      AS product,
        SUM(CASE WHEN o.ordered_at < :start_date THEN oi.line_total ELSE 0 END)     AS revenue_before,
        SUM(CASE WHEN o.ordered_at >= :start_date THEN oi.line_total ELSE 0 END)    AS revenue_now
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    JOIN products    AS p  ON p.product_id = oi.product_id
    WHERE o.branch_id = :branch_id
      AND o.ordered_at >= :previous_start
      AND o.ordered_at < date(:end_date, '+1 day')
    GROUP BY p.category_id, p.product_id, p.name
),
category_change AS (
    SELECT
        category_id,
        SUM(revenue_before)     AS revenue_before,
        SUM(revenue_now)        AS revenue_now
    FROM product_change
    GROUP BY category_id
),
ranked AS (
    SELECT
        pc.category_id,
        pc.product,
        pc.revenue_now - pc.revenue_before                                          AS product_change,
        ROW_NUMBER() OVER (
            PARTITION BY pc.category_id
            ORDER BY CASE WHEN cc.revenue_now >= cc.revenue_before
                          THEN pc.revenue_now - pc.revenue_before
                          ELSE pc.revenue_before - pc.revenue_now END DESC,
                     pc.product
        )                                                                           AS position
    FROM product_change AS pc
    JOIN category_change AS cc ON cc.category_id = pc.category_id
)
SELECT
    c.name                                      AS category,
    ROUND(cc.revenue_before, 2)                 AS revenue_before_qar,
    ROUND(cc.revenue_now, 2)                    AS revenue_now_qar,
    ROUND(cc.revenue_now - cc.revenue_before, 2) AS change_qar,
    r.product                                   AS main_product,
    ROUND(r.product_change, 2)                  AS main_product_change_qar
FROM category_change AS cc
JOIN categories AS c ON c.category_id = cc.category_id
JOIN ranked     AS r ON r.category_id = cc.category_id AND r.position = 1
ORDER BY ABS(cc.revenue_now - cc.revenue_before) DESC, category;
