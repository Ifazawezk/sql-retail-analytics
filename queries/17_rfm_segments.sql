-- Q17. How do customers split into RFM segments, and how much revenue does each segment bring?
-- Recency, frequency and monetary value are each scored 1 to 5 with NTILE,
-- measured on the day after the last order in the data. Segments use the
-- recency and frequency scores, which is the usual simplification.
WITH as_of AS (
    SELECT date(MAX(ordered_at), '+1 day') AS day FROM orders
),
customer_stats AS (
    SELECT
        o.customer_id,
        julianday((SELECT day FROM as_of)) - julianday(date(MAX(o.ordered_at))) AS recency_days,
        COUNT(DISTINCT o.order_id)                                              AS frequency,
        SUM(oi.line_total)                                                      AS monetary
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY o.customer_id
),
scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency_days DESC, customer_id) AS r_score,
        NTILE(5) OVER (ORDER BY frequency, customer_id)         AS f_score,
        NTILE(5) OVER (ORDER BY monetary, customer_id)          AS m_score
    FROM customer_stats
),
segmented AS (
    SELECT
        *,
        CASE
            WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
            WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
            WHEN r_score >= 4                  THEN 'Promising'
            WHEN r_score = 3                   THEN 'Needs attention'
            WHEN f_score >= 3                  THEN 'At risk'
            ELSE 'Lost'
        END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                                    AS customers,
    ROUND(AVG(recency_days), 0)                                 AS avg_recency_days,
    ROUND(AVG(frequency), 1)                                    AS avg_orders,
    ROUND(AVG(m_score), 1)                                      AS avg_m_score,
    ROUND(AVG(monetary), 2)                                     AS avg_spend_qar,
    ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS revenue_share_pct
FROM segmented
GROUP BY segment
ORDER BY revenue_share_pct DESC;
