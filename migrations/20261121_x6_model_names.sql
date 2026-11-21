-- Run in one transaction. Only repair the eight exact legacy model/color pairs.
-- Codes, quantities, prices and image references are preserved. Safe to rerun.
UPDATE products
SET model = CASE WHEN code LIKE 'X6-18 %' THEN 'X6-18' ELSE 'X6-20' END,
    color = SUBSTR(color, 4),
    updated_at = CURRENT_TIMESTAMP
WHERE model = 'X6'
  AND code = 'X6-' || color
  AND code IN (
      'X6-18 Cam', 'X6-18 Đỏ', 'X6-18 Dương', 'X6-18 Vàng',
      'X6-20 Cam', 'X6-20 Đỏ', 'X6-20 Dương', 'X6-20 Vàng'
  );

INSERT INTO app_settings (key, value)
VALUES ('catalog_cache_version', 'x6-model-fix-' || CAST(CURRENT_TIMESTAMP AS TEXT))
ON CONFLICT (key) DO UPDATE SET value = excluded.value;
