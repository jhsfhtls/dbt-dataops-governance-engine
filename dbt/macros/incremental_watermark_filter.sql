{% macro incremental_watermark_filter(watermark_column, lookback_days=3) -%}
  {{ return(adapter.dispatch('incremental_watermark_filter', 'dge_reference')(watermark_column, lookback_days)) }}
{%- endmacro %}

{% macro default__incremental_watermark_filter(watermark_column, lookback_days=3) -%}
{% if is_incremental() %}
WHERE {{ watermark_column }} >= (
    SELECT COALESCE(MAX({{ watermark_column }}), TIMESTAMP '1970-01-01 00:00:00') - INTERVAL '{{ lookback_days }} days'
    FROM {{ this }}
)
{% endif %}
{%- endmacro %}

{% macro snowflake__incremental_watermark_filter(watermark_column, lookback_days=3) -%}
{% if is_incremental() %}
WHERE {{ watermark_column }} >= (
    SELECT DATEADD('day', -{{ lookback_days }}, COALESCE(MAX({{ watermark_column }}), TO_TIMESTAMP('1970-01-01 00:00:00')))
    FROM {{ this }}
)
{% endif %}
{%- endmacro %}

{% macro spark__incremental_watermark_filter(watermark_column, lookback_days=3) -%}
{% if is_incremental() %}
WHERE {{ watermark_column }} >= (
    SELECT COALESCE(MAX({{ watermark_column }}), TIMESTAMP '1970-01-01 00:00:00') - INTERVAL {{ lookback_days }} DAYS
    FROM {{ this }}
)
{% endif %}
{%- endmacro %}

{% macro bigquery__incremental_watermark_filter(watermark_column, lookback_days=3) -%}
{% if is_incremental() %}
WHERE {{ watermark_column }} >= (
    SELECT TIMESTAMP_SUB(COALESCE(MAX({{ watermark_column }}), TIMESTAMP '1970-01-01 00:00:00'), INTERVAL {{ lookback_days }} DAY)
    FROM {{ this }}
)
{% endif %}
{%- endmacro %}
