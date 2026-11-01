-- How many days of Ramadan, Eid and the summer holidays fall in each of two periods?
-- Parameters: :previous_start, :start_date and :end_date (YYYY-MM-DD).
-- The earlier period runs from :previous_start to the day before :start_date, and
-- the current one from :start_date to :end_date, both included. Events are counted
-- by kind, so Eid al-Fitr in one period and Eid al-Adha in the other count as equal.
-- National Day is one day, so it is left out.
WITH RECURSIVE days(day) AS (
    SELECT :previous_start
    UNION ALL
    SELECT date(day, '+1 day')
    FROM days
    WHERE day < :end_date
)
SELECT
    e.kind,
    SUM(CASE WHEN d.day < :start_date THEN 1 ELSE 0 END)    AS days_before,
    SUM(CASE WHEN d.day >= :start_date THEN 1 ELSE 0 END)   AS days_now
FROM days AS d
JOIN calendar_events AS e ON d.day BETWEEN e.start_date AND e.end_date
WHERE e.kind IN ('ramadan', 'eid', 'season')
GROUP BY e.kind
ORDER BY MIN(e.start_date);
