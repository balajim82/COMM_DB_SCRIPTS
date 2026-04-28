DO $$
BEGIN
    PERFORM catalog.util_deep_merge_jsonb(
        'SystemData',
	    'SchedulerDiary',
	    'data',
	    '{"balaji_update_trade": "ABC123"}',
	    '{}'
    );
END $$;