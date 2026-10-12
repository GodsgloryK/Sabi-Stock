ALTER TABLE products ADD COLUMN IF NOT EXISTS sku TEXT;

WITH numbered AS (
    SELECT id,
           row_number() OVER (PARTITION BY business_id ORDER BY created_at, id) AS rn
    FROM products
    WHERE sku IS NULL
)
UPDATE products AS p
SET sku = 'SKU-' || lpad(numbered.rn::text, 4, '0')
FROM numbered
WHERE p.id = numbered.id;

ALTER TABLE products ALTER COLUMN sku SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'products_sku_check'
    ) THEN
        ALTER TABLE products
            ADD CONSTRAINT products_sku_check
            CHECK (length(trim(sku)) BETWEEN 1 AND 64);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS products_business_id_sku_unique_idx
    ON products (business_id, lower(sku));

CREATE TABLE IF NOT EXISTS product_sku_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    sku TEXT NOT NULL CHECK (length(trim(sku)) BETWEEN 1 AND 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS product_sku_registry_business_sku_unique
    ON product_sku_registry (business_id, lower(sku));

INSERT INTO product_sku_registry (business_id, sku)
SELECT business_id, sku FROM products
ON CONFLICT DO NOTHING;
