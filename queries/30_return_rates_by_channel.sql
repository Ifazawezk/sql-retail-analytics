-- Q30. Do delivered items come back more often than in-store items in each category, and what do refunds cost against gross profit?
-- Q09 gives one return rate per category. Here each category is split by the
-- channel of the original order, counting order lines, and a chi-square test on
-- the two-by-two table says whether the gap is more than chance. A value above
-- 3.84 is the usual 95% line, but with 14 rows one could cross it by luck. When
-- fewer than 5 delivery returns would be expected, the test is not reliable and
-- the row says so rather than guessing.
WITH returned AS (
    SELECT order_item_id, SUM(refund_amount) AS refund
    FROM returns
    GROUP BY order_item_id
),
lines AS (
    SELECT
        c.name                                              AS category,
        o.channel,
        oi.line_total - oi.quantity * oi.unit_cost          AS gross_profit,
        CASE WHEN r.order_item_id IS NULL THEN 0 ELSE 1 END AS came_back,
        COALESCE(r.refund, 0)                               AS refund
    FROM order_items AS oi
    JOIN orders     AS o ON o.order_id = oi.order_id
    JOIN products   AS p ON p.product_id = oi.product_id
    JOIN categories AS c ON c.category_id = p.category_id
    LEFT JOIN returned AS r ON r.order_item_id = oi.order_item_id
),
by_group AS (
    SELECT
        category,
        0                                                                   AS sort_key,
        1.0 * SUM(CASE WHEN channel = 'in_store' THEN came_back ELSE 0 END) AS store_back,
        1.0 * SUM(CASE WHEN channel = 'in_store' THEN 1 - came_back ELSE 0 END) AS store_kept,
        1.0 * SUM(CASE WHEN channel = 'delivery' THEN came_back ELSE 0 END) AS delivery_back,
        1.0 * SUM(CASE WHEN channel = 'delivery' THEN 1 - came_back ELSE 0 END) AS delivery_kept,
        SUM(refund)                                                         AS refunds,
        SUM(gross_profit)                                                   AS gross_profit
    FROM lines
    GROUP BY category
    UNION ALL
    SELECT
        'All categories', 1,
        1.0 * SUM(CASE WHEN channel = 'in_store' THEN came_back ELSE 0 END),
        1.0 * SUM(CASE WHEN channel = 'in_store' THEN 1 - came_back ELSE 0 END),
        1.0 * SUM(CASE WHEN channel = 'delivery' THEN came_back ELSE 0 END),
        1.0 * SUM(CASE WHEN channel = 'delivery' THEN 1 - came_back ELSE 0 END),
        SUM(refund),
        SUM(gross_profit)
    FROM lines
),
tested AS (
    SELECT
        *,
        store_back + store_kept         AS store_lines,
        delivery_back + delivery_kept   AS delivery_lines,
        (store_back + delivery_back) * (delivery_back + delivery_kept)
            / (store_back + store_kept + delivery_back + delivery_kept) AS expected_delivery_back,
        (store_back + store_kept + delivery_back + delivery_kept)
            * (store_back * delivery_kept - store_kept * delivery_back)
            * (store_back * delivery_kept - store_kept * delivery_back)
            / NULLIF((store_back + store_kept) * (delivery_back + delivery_kept)
                     * (store_back + delivery_back) * (store_kept + delivery_kept), 0) AS chi_square
    FROM by_group
)
SELECT
    category,
    CAST(store_lines AS INTEGER)                            AS in_store_lines,
    CAST(store_back AS INTEGER)                             AS in_store_returned,
    ROUND(100.0 * store_back / store_lines, 2)              AS in_store_rate_pct,
    CAST(delivery_lines AS INTEGER)                         AS delivery_lines,
    CAST(delivery_back AS INTEGER)                          AS delivery_returned,
    ROUND(100.0 * delivery_back / delivery_lines, 2)        AS delivery_rate_pct,
    ROUND((delivery_back / delivery_lines)
          / NULLIF(store_back / store_lines, 0), 2)         AS rate_ratio,
    ROUND(chi_square, 2)                                    AS chi_square,
    ROUND(100.0 * refunds / gross_profit, 1)                AS refunds_pct_of_gross_profit,
    CASE
        WHEN expected_delivery_back < 5 THEN 'Too few returns to say'
        WHEN chi_square < 3.84 THEN 'No clear difference'
        WHEN delivery_back / delivery_lines > store_back / store_lines THEN 'Higher on delivery'
        ELSE 'Lower on delivery'
    END                                                     AS delivery_vs_store
FROM tested
ORDER BY sort_key, delivery_rate_pct DESC;
