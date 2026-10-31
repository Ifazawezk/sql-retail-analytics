-- Which branches can a manager pick, and which dates have sales?
SELECT
    b.branch_id,
    b.name                      AS branch,
    b.opened_on,
    date(MIN(o.ordered_at))     AS first_order_day,
    date(MAX(o.ordered_at))     AS last_order_day
FROM branches AS b
JOIN orders AS o ON o.branch_id = b.branch_id
GROUP BY b.branch_id, b.name, b.opened_on
ORDER BY b.name;
