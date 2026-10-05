CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 160),
    category TEXT NOT NULL CHECK (length(trim(category)) BETWEEN 1 AND 80),
    buying_price NUMERIC(12, 2) NOT NULL CHECK (buying_price >= 0),
    selling_price NUMERIC(12, 2) NOT NULL CHECK (selling_price >= 0),
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS products_business_id_name_idx
    ON products (business_id, lower(name));

CREATE INDEX IF NOT EXISTS products_business_id_category_idx
    ON products (business_id, category);
