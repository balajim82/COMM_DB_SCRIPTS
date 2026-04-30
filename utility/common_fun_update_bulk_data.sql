CREATE OR REPLACE FUNCTION "public".util_deep_merge_jsonb(
    p_operation_type text,
    p_schema_name text,
    p_table_name text,
    p_column_name text,
    p_new_json text,
	p_append_keys text[] DEFAULT '{}'::text[],
    p_where_columns text[] DEFAULT NULL,
    p_where_values text[] DEFAULT NULL   
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_sql TEXT;
    v_where TEXT := '';
    i INT;
BEGIN
    -- Only UPDATE supported for now
    IF lower(p_operation_type) <> 'update' THEN
        RAISE EXCEPTION 'Unsupported operation type: %', p_operation_type;
    END IF;

    -- Build WHERE clause if values exist
    IF p_where_columns IS NOT NULL AND p_where_values IS NOT NULL 
	     AND array_length(p_where_columns,1) IS NOT NULL THEN
        
        IF array_length(p_where_columns,1) <> array_length(p_where_values,1) THEN
            RAISE EXCEPTION 'Mismatch between WHERE columns and values';
        END IF;

        v_where := ' WHERE ';

        FOR i IN 1..array_length(p_where_columns,1)
        LOOP
            IF i > 1 THEN
                v_where := v_where || ' AND ';
            END IF;

            v_where := v_where || format('%I = %L',
                p_where_columns[i],
                p_where_values[i]
            );
        END LOOP;
    END IF;

    -- Build UPDATE query
    v_sql := format(
        'UPDATE %I.%I
         SET %I = public.jsonb_deep_merge(%I, %L::jsonb, %L::text[])
         %s',
        p_schema_name,
        p_table_name,
        p_column_name,
        p_column_name,
        p_new_json,
        p_append_keys,
        v_where
    );

    -- Execute
    EXECUTE v_sql;

EXCEPTION
    WHEN others THEN
        RAISE EXCEPTION 'util_deep_merge_jsonb failed: %', SQLERRM;
END;
$$;

CREATE OR REPLACE FUNCTION "public".jsonb_deep_merge(
	target jsonb,
	source jsonb,
	append_keys text[] DEFAULT '{}'::text[])
    RETURNS jsonb
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE PARALLEL UNSAFE
AS $$
DECLARE
    key TEXT;
    result jsonb := target;
    val_target jsonb;
    val_source jsonb;
BEGIN
    IF target IS NULL THEN
        RETURN source;
    END IF;

    IF source IS NULL THEN
        RETURN target;
    END IF;

    -- Only objects can be deeply merged
    IF jsonb_typeof(target) <> 'object'
       OR jsonb_typeof(source) <> 'object' THEN
        RETURN source;
    END IF;

    FOR key IN SELECT jsonb_object_keys(source)
    LOOP
        val_target := target -> key;
        val_source := source -> key;

        -- Key exists in both
        IF val_target IS NOT NULL THEN

            -- object + object → recursive merge
            IF jsonb_typeof(val_target) = 'object'
               AND jsonb_typeof(val_source) = 'object' THEN

                result := jsonb_set(
                    result,
                    ARRAY[key],
                    jsonb_deep_merge(val_target, val_source, append_keys)
                );

            -- array + array → only append if key allowed
            ELSIF jsonb_typeof(val_target) = 'array'
               AND jsonb_typeof(val_source) = 'array'
               AND key = ANY(append_keys) THEN

                result := jsonb_set(
                    result,
                    ARRAY[key],
                    val_target || val_source
                );

            ELSE
                -- overwrite
                result := jsonb_set(result, ARRAY[key], val_source);
            END IF;

        ELSE
            -- new key → just add
            result := jsonb_set(result, ARRAY[key], val_source);
        END IF;
    END LOOP;

    RETURN result;
END;
$$;
