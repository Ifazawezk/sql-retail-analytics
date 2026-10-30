-- Q20. How do the branches rank each year once trading days and floor space are taken into account?
-- Lusail only opened in September 2024, so raw totals undersell it. Daily
-- revenue uses the days each branch was actually open in the year, and sales
-- density is annual revenue per square metre of floor space.
WITH years AS (
    SELECT DISTINCT strftime('%Y', ordered_at) AS year FROM orders
),
trading AS (
    SELECT
        y.year,
        b.branch_id,
        b.name,
        b.floor_area_sqm,
        julianday(y.year || '-12-31')
            - julianday(max(b.opened_on, y.year || '-01-01')) + 1  AS trading_days
    FROM years AS y
    CROSS JOIN branches AS b
    WHERE b.opened_on <= y.year || '-12-31'
),
revenue AS (
    SELECT
        strftime('%Y', o.ordered_at)    AS year,
        o.branch_id,
        SUM(oi.line_total)              AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY year, o.branch_id
),
scored AS (
    SELECT
        t.year,
        t.name                                              AS branch,
        CAST(t.trading_days AS INTEGER)                     AS trading_days,
        r.revenue,
        r.revenue / t.trading_days                          AS revenue_per_day,
        r.revenue * 365.0 / t.trading_days / t.floor_area_sqm AS sales_per_sqm
    FROM trading AS t
    JOIN revenue AS r ON r.year = t.year AND r.branch_id = t.branch_id
)
SELECT
    year,
    branch,
    trading_days,
    ROUND(revenue, 2)                                               AS revenue_qar,
    ROUND(revenue_per_day, 2)                                       AS revenue_per_day_qar,
    ROUND(sales_per_sqm, 2)                                         AS annual_sales_per_sqm_qar,
    RANK() OVER (PARTITION BY year ORDER BY revenue DESC)           AS rank_by_revenue,
    RANK() OVER (PARTITION BY year ORDER BY revenue_per_day DESC)   AS rank_by_daily_revenue,
    RANK() OVER (PARTITION BY year ORDER BY sales_per_sqm DESC)     AS rank_by_density
FROM scored
ORDER BY year, rank_by_daily_revenue;
