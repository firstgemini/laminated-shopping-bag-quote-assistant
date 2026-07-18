from pathlib import Path
import unittest

from quote_app.calculations import HANDLE_BODY, HANDLE_WEBBING, QuoteValidationError
from quote_app.quotation import (
    AddonItem,
    QuoteDraft,
    build_quotation_report,
)
from quote_app.repository import load_price_database


ROOT = Path(__file__).resolve().parents[1]


class QuotationReportTests(unittest.TestCase):
    def _draft(self, quantities=(1000, 5000, 10000), addons=()):
        database = load_price_database(ROOT / "price_database.xlsx")
        return database, QuoteDraft(
            width_cm=40,
            height_cm=35,
            gusset_cm=12,
            handle_length_cm=70,
            quantities=tuple(quantities),
            exchange_rate=6.7,
            material="PET材料（丽新布覆膜）",
            gsm_label="140克",
            handle_type=HANDLE_BODY,
            handle_width_cm=2.5,
            webbing_style=None,
            customer_info="Acme Buyer",
            addons=tuple(addons),
            database_fingerprint=database.fingerprint,
            company_name_en="Example Bags Ltd.",
            supplier_contact_en="Luke Xiang | Sales Manager",
        )

    def test_multiple_quantities_are_sorted_and_share_spec(self):
        database, draft = self._draft(quantities=(10000, 1000, 5000))
        material = database.material_record(draft.material, draft.gsm_label)
        report = build_quotation_report(
            draft,
            material_gsm=float(material["gsm"]),
            material_price_cny_per_m2=float(material["price_per_m2"]),
        )
        self.assertEqual([tier.quantity for tier in report.tiers], [1000, 5000, 10000])
        self.assertEqual(report.tiers[0].result.carton_count, 10)
        self.assertNotEqual(report.tiers[0].result.exw_cny, report.tiers[-1].result.exw_cny)

    def test_addons_apply_to_each_tier_without_changing_packing(self):
        addon = AddonItem("PP板", "PP board", 0.08)
        database, draft = self._draft(quantities=(1000, 5000), addons=(addon,))
        material = database.material_record(draft.material, draft.gsm_label)
        report = build_quotation_report(
            draft,
            material_gsm=float(material["gsm"]),
            material_price_cny_per_m2=float(material["price_per_m2"]),
        )
        for tier in report.tiers:
            self.assertAlmostEqual(tier.result.additional_cost_cny, 0.08)
        self.assertAlmostEqual(
            report.tiers[0].result.total_cbm,
            report.tiers[1].result.total_cbm / 5,
        )

    def test_duplicate_quantities_are_rejected(self):
        database, draft = self._draft(quantities=(1000, 1000))
        material = database.material_record(draft.material, draft.gsm_label)
        with self.assertRaisesRegex(QuoteValidationError, "不能重复"):
            build_quotation_report(
                draft,
                material_gsm=float(material["gsm"]),
                material_price_cny_per_m2=float(material["price_per_m2"]),
            )

    def test_special_webbing_uses_manual_price_and_conservative_weight(self):
        database, draft = self._draft(quantities=(1000,))
        draft = __import__("dataclasses").replace(
            draft,
            handle_type=HANDLE_WEBBING,
            handle_width_cm=2.5,
            webbing_style="特殊织带（手填价格）",
        )
        material = database.material_record(draft.material, draft.gsm_label)
        report = build_quotation_report(
            draft,
            material_gsm=float(material["gsm"]),
            material_price_cny_per_m2=float(material["price_per_m2"]),
            webbing_price_cny_per_m=0.5,
            webbing_g_per_m=20.0,
        )
        result = report.tiers[0].result
        self.assertAlmostEqual(result.handle_cost_cny, 0.735)
        self.assertAlmostEqual(result.webbing_price_cny_per_m, 0.5)
        self.assertGreater(result.bag_net_weight_kg, 0)
