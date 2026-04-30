DO $$
BEGIN
    PERFORM util_deep_merge_jsonb(
        'update',
        'SystemData',
        'SchedulerDiary',
        'data',
        '{
          "suri_new_trade": "RamaTrade"
        }',
        '{}',
        ARRAY['diary_record_id']::text[],
        ARRAY['000c2ef5-4d61-4aa6-bc0d-12fbda55678f']::text[]
    );
END $$;