-- Run this once in Supabase SQL Editor before syncing AMIS batch inventory.
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS amis_async_id VARCHAR;

CREATE UNIQUE INDEX IF NOT EXISTS uq_products_amis_async_id
    ON products (amis_async_id)
    WHERE amis_async_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS product_lots (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    stock_id INTEGER NOT NULL,
    batch_number VARCHAR NOT NULL,
    expiry_date TIMESTAMPTZ,
    quantity INTEGER NOT NULL DEFAULT 0,
    amis_product_async_id VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_product_lots_product_stock_batch
        UNIQUE (product_id, stock_id, batch_number)
);

CREATE INDEX IF NOT EXISTS ix_product_lots_product_id
    ON product_lots (product_id);

CREATE INDEX IF NOT EXISTS ix_product_lots_stock_batch
    ON product_lots (stock_id, batch_number);
