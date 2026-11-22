{% macro audit_run_metadata() -%}
  {{ return(adapter.dispatch('audit_run_metadata', 'dge_reference')()) }}
{%- endmacro %}

{% macro default__audit_run_metadata() -%}
    CAST('{{ invocation_id }}' AS VARCHAR) AS _dge_invocation_id,
    CAST(CURRENT_TIMESTAMP AS TIMESTAMP) AS _dge_loaded_at_utc,
    CAST('{{ this.name }}' AS VARCHAR) AS _dge_model_name
{%- endmacro %}

{% macro snowflake__audit_run_metadata() -%}
    CAST('{{ invocation_id }}' AS VARCHAR) AS _dge_invocation_id,
    CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_NTZ) AS _dge_loaded_at_utc,
    CAST('{{ this.name }}' AS VARCHAR) AS _dge_model_name
{%- endmacro %}

{% macro spark__audit_run_metadata() -%}
    CAST('{{ invocation_id }}' AS STRING) AS _dge_invocation_id,
    CAST(CURRENT_TIMESTAMP() AS TIMESTAMP) AS _dge_loaded_at_utc,
    CAST('{{ this.name }}' AS STRING) AS _dge_model_name
{%- endmacro %}

{% macro bigquery__audit_run_metadata() -%}
    CAST('{{ invocation_id }}' AS STRING) AS _dge_invocation_id,
    CAST(CURRENT_TIMESTAMP() AS TIMESTAMP) AS _dge_loaded_at_utc,
    CAST('{{ this.name }}' AS STRING) AS _dge_model_name
{%- endmacro %}
