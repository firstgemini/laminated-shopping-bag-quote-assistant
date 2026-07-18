from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quote_app.calculations import HANDLE_BODY
from quote_app.quotation import AddonItem, QuoteDraft, build_quotation_report
from quote_app.reports import generate_customer_pdf, generate_internal_pdf
from quote_app.repository import load_price_database


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf"

database = load_price_database(ROOT / "data" / "price_database.xlsx")
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
    supplier_contact_en="""Luke Xiang | Executive Sales Manager
Wenzhou Lianhai Bag Co., Ltd.

Mobile: +86 173 9809 9207 | Email: lhk@lianhaibag.com
Website: www.wenzhoulianhaibag.com

Factory Address: No. 1299, Keji Road, BSN Industrial Complex,
Wenzhou, Zhejiang, China 325802""",
)
report = build_quotation_report(
    draft,
    material_gsm=float(material["gsm"]),
    material_price_cny_per_m2=float(material["price_per_m2"]),
)
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "internal-costing-sample.pdf").write_bytes(generate_internal_pdf(report))
(OUTPUT / "customer-quotation-sample.pdf").write_bytes(generate_customer_pdf(report))
