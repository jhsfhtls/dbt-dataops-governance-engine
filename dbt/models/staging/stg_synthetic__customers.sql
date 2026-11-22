-- Standardized 1:1 staging model for synthetic customers with LGPD masking and key preservation
SELECT
    CAST(customer_id AS VARCHAR) AS customer_id,
    {{ generate_surrogate_key_strict(['customer_id']) }} AS customer_sk,
    {{ mask_lgpd_pii('full_name', mode='default') }} AS full_name_hash,
    {{ mask_lgpd_pii('cpf', mode='cpf') }} AS cpf_masked,
    {{ mask_lgpd_pii('email', mode='email') }} AS email_masked,
    {{ mask_lgpd_pii('phone', mode='phone') }} AS phone_masked,
    LPAD(TRIM(CAST(postal_code AS VARCHAR)), 8, '0') AS postal_code,
    COALESCE(
        NULLIF(NULLIF(UPPER(TRIM(CAST(customer_segment AS VARCHAR))), ''), 'N/A'),
        'UNCLASSIFIED'
    ) AS customer_segment,
    CAST(updated_at AS TIMESTAMP) AS updated_at
FROM {{ ref('raw_synthetic_customers') }}
