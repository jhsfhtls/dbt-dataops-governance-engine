{% macro generate_surrogate_key_strict(field_list) -%}
  {{ return(adapter.dispatch('generate_surrogate_key_strict', 'dge_reference')(field_list)) }}
{%- endmacro %}

{% macro _dge_sk_expr_list(field_list, str_type) -%}
  {%- set parts = [] -%}
  {%- for field in field_list -%}
    {%- do parts.append(
      "CASE WHEN " ~ field ~ " IS NULL THEN '__DGE_NULL__' "
      "WHEN TRIM(CAST(" ~ field ~ " AS " ~ str_type ~ ")) = '' THEN '__DGE_EMPTY__' "
      "ELSE TRIM(CAST(" ~ field ~ " AS " ~ str_type ~ ")) END"
    ) -%}
  {%- endfor -%}
  {{ return(parts) }}
{%- endmacro %}

{% macro default__generate_surrogate_key_strict(field_list) -%}
  {%- set parts = _dge_sk_expr_list(field_list, 'VARCHAR') -%}
  SHA256(CONCAT_WS('|', {{ parts | join(', ') }}))
{%- endmacro %}

{% macro snowflake__generate_surrogate_key_strict(field_list) -%}
  {%- set parts = _dge_sk_expr_list(field_list, 'VARCHAR') -%}
  SHA2(CONCAT_WS('|', {{ parts | join(', ') }}), 256)
{%- endmacro %}

{% macro spark__generate_surrogate_key_strict(field_list) -%}
  {%- set parts = _dge_sk_expr_list(field_list, 'STRING') -%}
  SHA2(CONCAT_WS('|', {{ parts | join(', ') }}), 256)
{%- endmacro %}

{% macro bigquery__generate_surrogate_key_strict(field_list) -%}
  {%- set parts = _dge_sk_expr_list(field_list, 'STRING') -%}
  TO_HEX(SHA256(ARRAY_TO_STRING([{{ parts | join(', ') }}], '|')))
{%- endmacro %}
