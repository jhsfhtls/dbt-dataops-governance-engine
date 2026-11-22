{{ config(materialized='table') }}

SELECT
    customer_id,
    customer_sk,
    full_name_hash,
    cpf_masked,
    email_masked,
    phone_masked,
    postal_code,
    customer_segment,
    updated_at,
    {{ audit_run_metadata() }}
FROM {{ ref('stg_synthetic__customers') }}
