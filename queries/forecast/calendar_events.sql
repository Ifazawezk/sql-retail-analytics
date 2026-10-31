-- Which dated events does the forecast know about in advance?
SELECT name, kind, start_date, end_date
FROM calendar_events
ORDER BY start_date;
