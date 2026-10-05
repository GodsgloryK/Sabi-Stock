CREATE UNIQUE INDEX IF NOT EXISTS products_id_business_id_unique_idx
    ON products (id, business_id);

CREATE TABLE IF NOT EXISTS sales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    selling_price NUMERIC(12, 2) NOT NULL CHECK (selling_price >= 0),
    buying_price NUMERIC(12, 2) NOT NULL CHECK (buying_price >= 0),
    profit NUMERIC(22, 2) NOT NULL,
    total_amount NUMERIC(22, 2) NOT NULL CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (product_id, business_id)
        REFERENCES products(id, business_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS sales_business_id_created_at_idx
    ON sales (business_id, created_at DESC);

CREATE INDEX IF NOT EXISTS sales_product_id_idx
    ON sales (product_id);
