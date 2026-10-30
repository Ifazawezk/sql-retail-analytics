-- Q06. How is the mix of payment methods changing from one year to the next?
SELECT
    strftime('%Y', ordered_at)                                      AS year,
    payment_method,
    COUNT(*)                                                        AS orders,
    ROUND(100.0 * COUNT(*)
          / SUM(COUNT(*)) OVER (PARTITION BY strftime('%Y', ordered_at)), 1) AS share_pct
FROM orders
GROUP BY year, payment_method
ORDER BY year, orders DESC;
