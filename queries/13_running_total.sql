-- Q13. What is the year-to-date revenue at the end of each month?
WITH monthly AS (
    SELECT
        strftime('%Y-%m', o.ordered_at) AS month,
        strftime('%Y', o.ordered_at)    AS year,
        SUM(oi.line_total)              AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY month, year
)
SELECT
    month,
    ROUND(revenue, 2)                                                   AS revenue_qar,
    ROUND(SUM(revenue) OVER ytd, 2)                                     AS year_to_date_qar,
    ROUND(100.0 * SUM(revenue) OVER ytd
          / SUM(revenue) OVER (PARTITION BY year), 1)                   AS pct_of_full_year
FROM monthly
WINDOW ytd AS (PARTITION BY year ORDER BY month
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
ORDER BY month;
