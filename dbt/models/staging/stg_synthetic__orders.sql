-- Standardized 1:1 staging model for synthetic orders with sentinel cleanup and safe division
SELECT
    CAST(order_id AS VARCHAR) AS order_id,
    {{ generate_surrogate_key_strict(['order_id']) }} AS order_sk,
    CAST(customer_id AS VARCHAR) AS customer_id,
    {{ generate_surrogate_key_strict(['customer_id']) }} AS customer_sk,
    NULLIF(UPPER(TRIM(CAST(order_status AS VARCHAR))), '') AS order_status,
    CAST(gross_amount_usd AS DOUBLE) AS gross_amount_usd,
    CAST(discount_usd AS DOUBLE) AS discount_usd,
    CAST(gross_amount_usd - discount_usd AS DOUBLE) AS net_amount_usd,
    CAST(discount_usd / NULLIF(gross_amount_usd, 0) AS DOUBLE) AS discount_rate,
    CAST(order_date AS DATE) AS order_date,
    CAST(updated_at AS TIMESTAMP) AS updated_at
FROM {{ ref('raw_synthetic_orders') }}
