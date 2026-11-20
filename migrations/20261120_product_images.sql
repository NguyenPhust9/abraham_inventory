-- Bounded image storage; no changes to existing product/image references.
CREATE TABLE IF NOT EXISTS public.product_images (
    digest VARCHAR(64) PRIMARY KEY,
    full_data BYTEA NOT NULL,
    thumb_data BYTEA NOT NULL,
    full_size INTEGER NOT NULL CHECK (full_size > 0 AND full_size <= 204800),
    thumb_size INTEGER NOT NULL CHECK (thumb_size > 0 AND thumb_size <= 51200),
    width INTEGER NOT NULL CHECK (width > 0 AND width <= 1280),
    height INTEGER NOT NULL CHECK (height > 0 AND height <= 1280),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Only the server database role accesses bytes. Public reads use the cached media route.
ALTER TABLE public.product_images ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_images FROM anon, authenticated;
