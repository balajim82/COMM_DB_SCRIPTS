DO $$
BEGIN
    PERFORM catalog.util_deep_merge_jsonb(
        'OrgData',
	    'users_details',
	    'USR_DATA',
	    '{"update_at": "28-Apr-26"}',
	    '{}'
    );
END $$;