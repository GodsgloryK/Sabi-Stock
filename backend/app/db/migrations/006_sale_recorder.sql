ALTER TABLE sales ADD COLUMN IF NOT EXISTS recorded_by_user_id UUID
    REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS sales_recorded_by_user_id_idx
    ON sales (recorded_by_user_id);

UPDATE sales AS s
SET recorded_by_user_id = b.owner_user_id
FROM businesses AS b
WHERE b.id = s.business_id AND s.recorded_by_user_id IS NULL;
