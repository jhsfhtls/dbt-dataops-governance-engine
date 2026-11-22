{{ config(materialized='table') }}

SELECT
    {{ generate_surrogate_key_strict(['c.customer_segment', 'o.order_date']) }} AS segment_date_sk,
    c.customer_segment,
    o.order_date,
    CAST(COUNT(DISTINCT o.order_id) AS BIGINT) AS order_count,
    CAST(COUNT(DISTINCT o.customer_sk) AS BIGINT) AS active_customers,
    CAST(SUM(o.gross_amount_usd) AS DOUBLE) AS total_gross_usd,
    CAST(SUM(o.net_amount_usd) AS DOUBLE) AS total_net_usd,
    CAST(SUM(o.discount_usd) / NULLIF(SUM(o.gross_amount_usd), 0) AS DOUBLE) AS effective_discount_rate,
    {{ audit_run_metadata() }}
FROM {{ ref('fct_orders') }} AS o
INNER JOIN {{ ref('dim_customers') }} AS c
    ON o.customer_sk = c.customer_sk
WHERE o.order_status IN ('PAID', 'PENDING')
GROUP BY
    c.customer_segment,
    o.order_date
