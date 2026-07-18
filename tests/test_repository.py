from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from quote_app.repository import (
    PriceDatabaseError,
    install_price_database,
    load_price_database,
    validate_frames,
)


ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def test_current_workbook_uses_color_webbing_price(self):
        database = load_price_database(ROOT / "price_database.xlsx")
        record = database.webbing_record("普通花纹", 2.5)
        self.assertAlmostEqual(float(record["price_per_m"]), 0.16)
        self.assertAlmostEqual(float(record["grams_per_m"]), 10.18)
        material = database.material_record("无纺布覆膜二等材料", "155克")
        self.assertAlmostEqual(float(material["price_per_m2"]), 1.71)
        self.assertFalse(any("155克" in warning for warning in database.warnings))

    def test_simplified_webbing_schema_is_supported(self):
        frames = {
            "袋身材料": pd.DataFrame(
                {
                    "材料分类": ["测试材料"],
                    "规格克重": ["100克"],
                    "每平方米单价(元)": [1.2],
                }
            ),
            "织带材料": pd.DataFrame(
                {
                    "样式": ["平纹"],
                    "宽度（公分）": [2.5],
                    "每米克重": [8.0],
                    "每米单价（元）": [0.15],
                }
            ),
        }
        database = validate_frames(
            frames,
            modified_at=datetime.now(timezone.utc),
            fingerprint="test",
        )
        self.assertEqual(database.webbing_styles(), ["平纹"])
        self.assertEqual(database.webbing_widths("平纹"), [2.5])

    def test_duplicate_lookup_key_is_rejected(self):
        frames = {
            "袋身材料": pd.DataFrame(
                {
                    "材料分类": ["测试材料", "测试材料"],
                    "规格克重": ["100克", "100克"],
                    "每平方米单价(元)": [1.2, 1.3],
                }
            ),
            "织带材料": pd.DataFrame(
                {
                    "样式": ["平纹"],
                    "宽度（公分）": [2.5],
                    "每米克重": [8.0],
                    "每米单价（元）": [0.15],
                }
            ),
        }
        with self.assertRaisesRegex(PriceDatabaseError, "查价键重复"):
            validate_frames(
                frames,
                modified_at=datetime.now(timezone.utc),
                fingerprint="test",
            )

    def test_install_keeps_valid_backup(self):
        source = (ROOT / "price_database.xlsx").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            target = data_dir / "price_database.xlsx"
            target.write_bytes(source)
            result = install_price_database(
                source,
                target_path=target,
                backup_dir=data_dir / "backups",
            )
            self.assertEqual(target.read_bytes(), source)
            self.assertTrue(list((data_dir / "backups").glob("*.xlsx")))
            self.assertEqual(result.fingerprint, load_price_database(target).fingerprint)


if __name__ == "__main__":
    unittest.main()
