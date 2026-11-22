{% macro mask_lgpd_pii(column_name, mode='default') -%}
  {{ return(adapter.dispatch('mask_lgpd_pii', 'dge_reference')(column_name, mode)) }}
{%- endmacro %}

{% macro default__mask_lgpd_pii(column_name, mode='default') -%}
  {%- if mode == 'cpf' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***', SUBSTR(CAST({{ column_name }} AS VARCHAR), 4, 3), '***-**') END
  {%- elif mode == 'email' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***@', SPLIT_PART(CAST({{ column_name }} AS VARCHAR), '@', 2)) END
  {%- elif mode == 'phone' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('****-', RIGHT(CAST({{ column_name }} AS VARCHAR), 4)) END
  {%- else -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE SHA256(CAST({{ column_name }} AS VARCHAR)) END
  {%- endif -%}
{%- endmacro %}

{% macro snowflake__mask_lgpd_pii(column_name, mode='default') -%}
  {%- if mode == 'cpf' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***', SUBSTR(CAST({{ column_name }} AS VARCHAR), 4, 3), '***-**') END
  {%- elif mode == 'email' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***@', SPLIT_PART(CAST({{ column_name }} AS VARCHAR), '@', 2)) END
  {%- elif mode == 'phone' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('****-', RIGHT(CAST({{ column_name }} AS VARCHAR), 4)) END
  {%- else -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE SHA2(CAST({{ column_name }} AS VARCHAR), 256) END
  {%- endif -%}
{%- endmacro %}

{% macro spark__mask_lgpd_pii(column_name, mode='default') -%}
  {%- if mode == 'cpf' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***', SUBSTRING(CAST({{ column_name }} AS STRING), 4, 3), '***-**') END
  {%- elif mode == 'email' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***@', ELEMENT_AT(SPLIT(CAST({{ column_name }} AS STRING), '@'), 2)) END
  {%- elif mode == 'phone' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('****-', RIGHT(CAST({{ column_name }} AS STRING), 4)) END
  {%- else -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE SHA2(CAST({{ column_name }} AS STRING), 256) END
  {%- endif -%}
{%- endmacro %}

{% macro bigquery__mask_lgpd_pii(column_name, mode='default') -%}
  {%- if mode == 'cpf' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***', SUBSTR(CAST({{ column_name }} AS STRING), 4, 3), '***-**') END
  {%- elif mode == 'email' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('***@', SPLIT(CAST({{ column_name }} AS STRING), '@')[SAFE_OFFSET(1)]) END
  {%- elif mode == 'phone' -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE CONCAT('****-', RIGHT(CAST({{ column_name }} AS STRING), 4)) END
  {%- else -%}
    CASE WHEN {{ column_name }} IS NULL THEN NULL ELSE TO_HEX(SHA256(CAST({{ column_name }} AS STRING))) END
  {%- endif -%}
{%- endmacro %}
