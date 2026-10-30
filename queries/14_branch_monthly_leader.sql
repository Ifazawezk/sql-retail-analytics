-- Q14. Which branch led each month on revenue, and by how much over the runner-up?
WITH branch_month AS (
    SELECT
        strftime('%Y-%m', o.ordered_at) AS month,
        o.branch_id,
        SUM(oi.line_total)              AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY month, o.branch_id
),
ranked AS (
    SELECT
        bm.month,
        b.name                                          AS branch,
        bm.revenue,
        ROW_NUMBER() OVER (PARTITION BY bm.month
                           ORDER BY bm.revenue DESC, b.name) AS position,
        COUNT(*) OVER (PARTITION BY bm.month)           AS branches_trading
    FROM branch_month AS bm
    JOIN branches AS b ON b.branch_id = bm.branch_id
)
SELECT
    month,
    MAX(CASE WHEN position = 1 THEN branch END)                     AS leader,
    ROUND(MAX(CASE WHEN position = 1 THEN revenue END), 2)          AS leader_revenue_qar,
    MAX(CASE WHEN position = 2 THEN branch END)                     AS runner_up,
    ROUND(MAX(CASE WHEN position = 1 THEN revenue END)
          - MAX(CASE WHEN position = 2 THEN revenue END), 2)        AS lead_qar,
    MAX(branches_trading)                                           AS branches_trading
FROM ranked
GROUP BY month
ORDER BY month;
