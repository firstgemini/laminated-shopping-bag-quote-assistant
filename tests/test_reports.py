from pathlib import Path
import unittest

from pypdf import PdfReader

from quote_app.calculations import HANDLE_BODY
from quote_app.quotation import AddonItem, QuoteDraft, build_quotation_report
from quote_app.reports import generate_customer_pdf, generate_internal_pdf
from quote_app.repository import load_price_database


ROOT = Path(__file__).resolve().parents[1]


class ReportTests(unittest.TestCase):
    def _report(self):
        database = load_price_database(ROOT / "price_database.xlsx")
        material = database.material_record("PET材料（丽新布覆膜）", "140克")
        draft = QuoteDraft(
            width_cm=40,
            height_cm=35,
            gusset_cm=12,
            handle_length_cm=70,
            quantities=(1000, 5000, 10000),
            exchange_rate=6.7,
            material="PET材料（丽新布覆膜）",
            gsm_label="140克",
            handle_type=HANDLE_BODY,
            handle_width_cm=2.5,
            webbing_style=None,
            customer_info="Acme Buyer\nLondon, UK",
            addons=(AddonItem("PP板", "PP board", 0.08),),
            database_fingerprint=database.fingerprint,
            company_name_en="Example Bags Ltd.",
            supplier_contact_en="Luke Xiang | Sales Manager\ncontact@example.com",
        )
        return build_quotation_report(
            draft,
            material_gsm=float(material["gsm"]),
            material_price_cny_per_m2=float(material["price_per_m2"]),
        )

    def test_internal_pdf_contains_cost_data(self):
        pdf = generate_internal_pdf(self._report())
        text = "\n".join(page.extract_text() or "" for page in PdfReader(__import__("io").BytesIO(pdf)).pages)
        self.assertIn("EXW CNY", text)
        self.assertIn("FOB CNY", text)
        self.assertIn("176cm", text)
        self.assertGreater(len(pdf), 10_000)

    def test_customer_pdf_is_english_and_hides_internal_costs(self):
        pdf = generate_customer_pdf(self._report())
        text = "\n".join(page.extract_text() or "" for page in PdfReader(__import__("io").BytesIO(pdf)).pages)
        self.assertIn("Customer Information", text)
        self.assertIn("Quantity Price Schedule", text)
        self.assertIn("EXW USD/pc", text)
        self.assertIn("FOB Ningbo USD/pc", text)
        self.assertIn("PP board", text)
        self.assertIn("Supplier Contact", text)
        self.assertIn("contact@example.com", text)
        self.assertNotIn("人民币", text)
        self.assertNotIn("工厂利润", text)
        self.assertNotIn("损耗", text)

    def test_customer_pdf_is_landscape_a4(self):
        reader = PdfReader(__import__("io").BytesIO(generate_customer_pdf(self._report())))
        page = reader.pages[0]
        self.assertGreater(float(page.mediabox.width), float(page.mediabox.height))
        self.assertAlmostEqual(float(page.mediabox.width), 841.89, delta=1)
        self.assertAlmostEqual(float(page.mediabox.height), 595.28, delta=1)
