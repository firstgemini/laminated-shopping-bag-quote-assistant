from pathlib import Path
import tempfile
import unittest

from quote_app.settings import (
    DEFAULT_EXCHANGE_RATE,
    DEFAULT_SUPPLIER_CONTACT_EN,
    load_settings,
    save_company_name,
    save_exchange_rate,
    save_supplier_contact,
)


class SettingsTests(unittest.TestCase):
    def test_missing_settings_uses_default(self):
        with tempfile.TemporaryDirectory() as directory:
            result = load_settings(Path(directory) / "missing.json")
            self.assertEqual(result.settings.exchange_rate, DEFAULT_EXCHANGE_RATE)
            self.assertEqual(
                result.settings.supplier_contact_en, DEFAULT_SUPPLIER_CONTACT_EN
            )
            self.assertIsNone(result.warning)

    def test_saved_exchange_rate_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            save_exchange_rate(path, 6.8)
            result = load_settings(path)
            self.assertEqual(result.settings.exchange_rate, 6.8)
            self.assertEqual(result.settings.company_name_en, "")
            self.assertEqual(
                result.settings.supplier_contact_en, DEFAULT_SUPPLIER_CONTACT_EN
            )
            self.assertIsNone(result.warning)

    def test_company_name_preserves_exchange_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            save_exchange_rate(path, 6.8)
            save_company_name(path, "Example Bags Ltd.")
            result = load_settings(path)
            self.assertEqual(result.settings.exchange_rate, 6.8)
            self.assertEqual(result.settings.company_name_en, "Example Bags Ltd.")

    def test_supplier_contact_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            save_exchange_rate(path, 6.8)
            save_company_name(path, "Example Bags Ltd.")
            save_supplier_contact(path, "Alternate Sales Contact")
            result = load_settings(path)
            self.assertEqual(result.settings.exchange_rate, 6.8)
            self.assertEqual(result.settings.company_name_en, "Example Bags Ltd.")
            self.assertEqual(
                result.settings.supplier_contact_en, "Alternate Sales Contact"
            )

    def test_corrupt_settings_falls_back_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            path.write_text("not-json", encoding="utf-8")
            result = load_settings(path)
            self.assertEqual(result.settings.exchange_rate, DEFAULT_EXCHANGE_RATE)
            self.assertIsNotNone(result.warning)


if __name__ == "__main__":
    unittest.main()
