-- Q18. Of the customers who first shopped in a given month, what share came back 1, 2, 3, 6 and 12 months later?
-- Customers are grouped by the month of their first order. A blank (NULL)
-- cell means that month falls after the end of the data.
WITH customer_months AS (
    SELECT DISTINCT
        customer_id,
        CAST(strftime('%Y', ordered_at) AS INTEGER) * 12
            + CAST(strftime('%m', ordered_at) AS INTEGER) - 1   AS month_index
    FROM orders
),
cohorts AS (
    SELECT customer_id, MIN(month_index) AS cohort_index
    FROM customer_months
    GROUP BY customer_id
),
activity AS (
    SELECT
        c.cohort_index,
        cm.customer_id,
        cm.month_index - c.cohort_index AS months_since_first
    FROM customer_months AS cm
    JOIN cohorts AS c ON c.customer_id = cm.customer_id
),
last_month AS (
    SELECT MAX(month_index) AS month_index FROM customer_months
)
SELECT
    printf('%04d-%02d', a.cohort_index / 12, a.cohort_index % 12 + 1)  AS cohort,
    COUNT(DISTINCT a.customer_id)                                       AS customers,
    CASE WHEN a.cohort_index + 1 <= lm.month_index THEN ROUND(100.0
        * COUNT(DISTINCT CASE WHEN a.months_since_first = 1 THEN a.customer_id END)
        / COUNT(DISTINCT a.customer_id), 1) END                         AS month_1_pct,
    CASE WHEN a.cohort_index + 2 <= lm.month_index THEN ROUND(100.0
        * COUNT(DISTINCT CASE WHEN a.months_since_first = 2 THEN a.customer_id END)
        / COUNT(DISTINCT a.customer_id), 1) END                         AS month_2_pct,
    CASE WHEN a.cohort_index + 3 <= lm.month_index THEN ROUND(100.0
        * COUNT(DISTINCT CASE WHEN a.months_since_first = 3 THEN a.customer_id END)
        / COUNT(DISTINCT a.customer_id), 1) END                         AS month_3_pct,
    CASE WHEN a.cohort_index + 6 <= lm.month_index THEN ROUND(100.0
        * COUNT(DISTINCT CASE WHEN a.months_since_first = 6 THEN a.customer_id END)
        / COUNT(DISTINCT a.customer_id), 1) END                         AS month_6_pct,
    CASE WHEN a.cohort_index + 12 <= lm.month_index THEN ROUND(100.0
        * COUNT(DISTINCT CASE WHEN a.months_since_first = 12 THEN a.customer_id END)
        / COUNT(DISTINCT a.customer_id), 1) END                         AS month_12_pct
FROM activity AS a
CROSS JOIN last_month AS lm
GROUP BY a.cohort_index, lm.month_index
ORDER BY a.cohort_index;
