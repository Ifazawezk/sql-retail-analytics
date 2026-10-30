-- Q11. How did revenue change from one month to the next?
WITH monthly AS (
    SELECT
        strftime('%Y-%m', o.ordered_at) AS month,
        SUM(oi.line_total)              AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY month
)
SELECT
    month,
    ROUND(revenue, 2)                                   AS revenue_qar,
    ROUND(LAG(revenue) OVER w, 2)                       AS previous_month_qar,
    ROUND(revenue - LAG(revenue) OVER w, 2)             AS change_qar,
    ROUND(100.0 * (revenue - LAG(revenue) OVER w)
          / LAG(revenue) OVER w, 1)                     AS mom_change_pct
FROM monthly
WINDOW w AS (ORDER BY month)
ORDER BY month;
