-- Q28. Which products stopped selling at a branch for longer than normal demand can explain?
-- There is no stock table, so a stock-out can only be inferred from a gap in
-- sales. A gap alone proves little, because a quiet month, Ramadan or the summer
-- can each explain one. Each gap gets two estimates of the sales it should have
-- had: the orders the branch took in the gap times the product's usual rate at
-- that branch, and the same orders times its rate at the other branches over
-- the same days, adjusted for how much this branch favours the product. The
-- lower one is used, so both have to agree that a sale was due.
-- The line of 12 expected sales comes from testing, not theory. The generator
-- never takes a product off the shelf, so every gap in the sample data is
-- chance, and across 11 seeds of about 3,000 gaps each the score never reached
-- 12. A test removes real sales to prove that a long gap in a best seller is
-- found. Shorter gaps and slower products cannot be told from chance at these
-- volumes: a month without the single best seller scores just under the line.
WITH bounds AS (
    SELECT date(MAX(ordered_at), '+1 day') AS end_of_data FROM orders
),
sales AS (
    SELECT o.branch_id, oi.product_id, date(o.ordered_at) AS day, oi.line_total
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
),
-- Only pairs that sell often enough for a gap to mean anything.
pairs AS (
    SELECT branch_id, product_id, COUNT(*) AS lines, AVG(line_total) AS avg_line_value
    FROM sales
    GROUP BY branch_id, product_id
    HAVING COUNT(*) >= 40
),
sale_days AS (
    SELECT DISTINCT s.branch_id, s.product_id, s.day
    FROM sales AS s
    JOIN pairs AS p ON p.branch_id = s.branch_id AND p.product_id = s.product_id
),
-- A gap can still be open when the data ends, so the last one runs to the end.
gaps AS (
    SELECT
        branch_id,
        product_id,
        day                                                         AS last_sale,
        COALESCE(LEAD(day) OVER (PARTITION BY branch_id, product_id ORDER BY day),
                 (SELECT end_of_data FROM bounds))                  AS next_sale
    FROM sale_days
),
long_gaps AS (
    SELECT *, CAST(julianday(next_sale) - julianday(last_sale) - 1 AS INTEGER) AS gap_days
    FROM gaps
    WHERE julianday(next_sale) - julianday(last_sale) - 1 >= 14
),
branch_totals AS (
    SELECT branch_id, COUNT(*) AS orders FROM orders GROUP BY branch_id
),
product_totals AS (
    SELECT product_id, COUNT(*) AS lines FROM order_items GROUP BY product_id
),
order_total AS (
    SELECT COUNT(*) AS orders FROM orders
),
evidence AS (
    SELECT
        g.*,
        (SELECT COUNT(*) FROM orders AS o
          WHERE o.branch_id = g.branch_id
            AND o.ordered_at >= date(g.last_sale, '+1 day')
            AND o.ordered_at < g.next_sale)                         AS orders_here,
        (SELECT COUNT(*) FROM orders AS o
          WHERE o.branch_id <> g.branch_id
            AND o.ordered_at >= date(g.last_sale, '+1 day')
            AND o.ordered_at < g.next_sale)                         AS orders_elsewhere,
        (SELECT COUNT(*) FROM order_items AS oi
           JOIN orders AS o ON o.order_id = oi.order_id
          WHERE oi.product_id = g.product_id
            AND o.branch_id <> g.branch_id
            AND o.ordered_at >= date(g.last_sale, '+1 day')
            AND o.ordered_at < g.next_sale)                         AS lines_elsewhere
    FROM long_gaps AS g
),
estimates AS (
    SELECT
        e.branch_id,
        e.product_id,
        e.last_sale,
        e.next_sale,
        e.gap_days,
        e.orders_here,
        p.avg_line_value,
        e.orders_here * (1.0 * p.lines / bt.orders)                 AS usual_rate_estimate,
        e.orders_here * (1.0 * e.lines_elsewhere / NULLIF(e.orders_elsewhere, 0))
            * ((1.0 * p.lines / bt.orders)
               / ((1.0 * pt.lines - p.lines) / (ot.orders - bt.orders))) AS elsewhere_estimate
    FROM evidence AS e
    JOIN pairs AS p ON p.branch_id = e.branch_id AND p.product_id = e.product_id
    JOIN branch_totals AS bt ON bt.branch_id = e.branch_id
    JOIN product_totals AS pt ON pt.product_id = e.product_id
    CROSS JOIN order_total AS ot
),
scored AS (
    SELECT *, min(usual_rate_estimate, COALESCE(elsewhere_estimate, usual_rate_estimate)) AS expected_sales
    FROM estimates
)
SELECT
    b.name                                                  AS branch,
    pr.name                                                 AS product,
    s.last_sale,
    s.next_sale,
    s.gap_days,
    s.orders_here                                           AS orders_in_gap,
    ROUND(s.expected_sales, 1)                              AS expected_sales,
    ROUND(s.expected_sales * s.avg_line_value, 2)           AS revenue_at_risk_qar,
    CASE WHEN s.expected_sales >= 12 THEN 'Likely stock-out'
         ELSE 'Within normal variation' END                 AS assessment
FROM scored AS s
JOIN branches AS b  ON b.branch_id = s.branch_id
JOIN products AS pr ON pr.product_id = s.product_id
ORDER BY s.expected_sales DESC, branch, product
LIMIT 15;
