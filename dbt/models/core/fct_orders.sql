{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='order_id',
        on_schema_change='append_new_columns'
    )
}}

SELECT
    order_id,
    order_sk,
    customer_id,
    customer_sk,
    order_status,
    gross_amount_usd,
    discount_usd,
    net_amount_usd,
    discount_rate,
    order_date,
    updated_at,
    {{ audit_run_metadata() }}
FROM {{ ref('stg_synthetic__orders') }}
{{ incremental_watermark_filter('updated_at', lookback_days=3) }}
