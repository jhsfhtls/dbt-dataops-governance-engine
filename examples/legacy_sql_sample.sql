-- Synthetic legacy analytical SQL example containing common FinOps, modeling, quality, and LGPD anti-patterns.
SELECT DISTINCT
    *,
    o.discount_usd / o.gross_amount_usd AS discount_rate,
    c.cpf,
    c.email
FROM analytics_legacy.raw_orders AS o
CROSS JOIN analytics_legacy.raw_customers AS c
WHERE EXTRACT(YEAR FROM o.order_date) = 2026
ORDER BY o.order_date DESC;
