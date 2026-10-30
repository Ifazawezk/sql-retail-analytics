-- Q23. How much revenue and margin comes from discounted lines compared with full-price lines?
SELECT
    strftime('%Y', o.ordered_at)                                        AS year,
    CASE WHEN oi.discount_amount > 0 THEN 'Discounted' ELSE 'Full price' END AS price_type,
    COUNT(*)                                                            AS lines,
    SUM(oi.quantity)                                                    AS units,
    ROUND(SUM(oi.line_total), 2)                                        AS revenue_qar,
    ROUND(100.0 * SUM(oi.line_total)
          / SUM(SUM(oi.line_total)) OVER (PARTITION BY strftime('%Y', o.ordered_at)), 1) AS revenue_share_pct,
    ROUND(SUM(oi.discount_amount), 2)                                   AS discount_given_qar,
    ROUND(100.0 * SUM(oi.discount_amount)
          / SUM(oi.quantity * oi.unit_price), 1)                        AS avg_discount_pct,
    ROUND(100.0 * SUM(oi.line_total - oi.quantity * oi.unit_cost)
          / SUM(oi.line_total), 1)                                      AS gross_margin_pct
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
GROUP BY year, price_type
ORDER BY year, price_type;
