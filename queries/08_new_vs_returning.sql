-- Q08. How many customers shop each month, and how many of them are new?
WITH first_orders AS (
    SELECT customer_id, MIN(strftime('%Y-%m', ordered_at)) AS first_month
    FROM orders
    GROUP BY customer_id
),
monthly AS (
    SELECT
        strftime('%Y-%m', o.ordered_at)                                 AS month,
        COUNT(DISTINCT o.customer_id)                                   AS active_customers,
        COUNT(DISTINCT CASE WHEN f.first_month = strftime('%Y-%m', o.ordered_at)
                            THEN o.customer_id END)                     AS new_customers
    FROM orders AS o
    JOIN first_orders AS f ON f.customer_id = o.customer_id
    GROUP BY month
)
SELECT
    month,
    active_customers,
    new_customers,
    active_customers - new_customers            AS returning_customers,
    SUM(new_customers) OVER (ORDER BY month)    AS customers_to_date
FROM monthly
ORDER BY month;
