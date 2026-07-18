from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from quote_app.calculations import (
    QuoteInputs,
    QuoteResult,
    QuoteValidationError,
    calculate_quote,
)


MAX_QUANTITY_TIERS = 10


@dataclass(frozen=True)
class AddonItem:
    internal_name: str
    english_name: str
    unit_cost_cny: float


@dataclass(frozen=True)
class QuoteDraft:
    width_cm: float
    height_cm: float
    gusset_cm: float
    handle_length_cm: float
    quantities: tuple[int, ...]
    exchange_rate: float
    material: str
    gsm_label: str
    handle_type: str
    handle_width_cm: float
    webbing_style: str | None
    customer_info: str
    addons: tuple[AddonItem, ...]
    database_fingerprint: str
    company_name_en: str
    supplier_contact_en: str


@dataclass(frozen=True)
class QuoteSnapshot:
    draft: QuoteDraft
    submitted_at: datetime
    material_gsm: float
    material_price_cny_per_m2: float
    webbing_price_cny_per_m: float | None
    webbing_g_per_m: float | None


@dataclass(frozen=True)
class TierQuoteResult:
    quantity: int
    result: QuoteResult


@dataclass(frozen=True)
class QuotationReport:
    snapshot: QuoteSnapshot
    tiers: tuple[TierQuoteResult, ...]


def normalize_draft(draft: QuoteDraft) -> QuoteDraft:
    normalized_addons = tuple(
        AddonItem(
            internal_name=item.internal_name.strip(),
            english_name=item.english_name.strip(),
            unit_cost_cny=float(item.unit_cost_cny),
        )
        for item in draft.addons
        if item.internal_name.strip()
        or item.english_name.strip()
        or float(item.unit_cost_cny) != 0
    )
    return replace(
        draft,
        quantities=tuple(sorted(int(quantity) for quantity in draft.quantities)),
        customer_info=draft.customer_info.strip(),
        addons=normalized_addons,
        company_name_en=draft.company_name_en.strip(),
        supplier_contact_en=draft.supplier_contact_en.strip(),
    )


def validate_draft(draft: QuoteDraft) -> None:
    if not draft.quantities:
        raise QuoteValidationError("请至少填写一个数量。")
    if len(draft.quantities) > MAX_QUANTITY_TIERS:
        raise QuoteValidationError(f"数量阶梯最多{MAX_QUANTITY_TIERS}个。")
    if len(set(draft.quantities)) != len(draft.quantities):
        raise QuoteValidationError("数量阶梯不能重复。")
    for quantity in draft.quantities:
        if quantity < 100 or quantity % 100 != 0:
            raise QuoteValidationError("每个数量必须是100的整数倍。")

    for item in draft.addons:
        if item.unit_cost_cny < 0:
            raise QuoteValidationError("附加项目单价不能为负数。")
        if not item.internal_name:
            raise QuoteValidationError("附加项目必须填写内部名称。")
        if item.unit_cost_cny == 0:
            raise QuoteValidationError(
                f"附加项目“{item.internal_name}”的单价必须大于0。"
            )


def build_quotation_report(
    draft: QuoteDraft,
    *,
    material_gsm: float,
    material_price_cny_per_m2: float,
    webbing_price_cny_per_m: float | None = None,
    webbing_g_per_m: float | None = None,
    submitted_at: datetime | None = None,
) -> QuotationReport:
    normalized = normalize_draft(draft)
    validate_draft(normalized)
    submitted = submitted_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    additional_unit_cost = sum(item.unit_cost_cny for item in normalized.addons)

    tiers: list[TierQuoteResult] = []
    for quantity in normalized.quantities:
        inputs = QuoteInputs(
            width_cm=normalized.width_cm,
            height_cm=normalized.height_cm,
            gusset_cm=normalized.gusset_cm,
            handle_length_cm=normalized.handle_length_cm,
            quantity=quantity,
            exchange_rate=normalized.exchange_rate,
            material=normalized.material,
            gsm_label=normalized.gsm_label,
            handle_type=normalized.handle_type,
            handle_width_cm=normalized.handle_width_cm,
            webbing_style=normalized.webbing_style,
        )
        result = calculate_quote(
            inputs,
            material_price_cny_per_m2=material_price_cny_per_m2,
            material_gsm=material_gsm,
            webbing_price_cny_per_m=webbing_price_cny_per_m,
            webbing_g_per_m=webbing_g_per_m,
            additional_unit_cost_cny=additional_unit_cost,
        )
        tiers.append(TierQuoteResult(quantity=quantity, result=result))

    snapshot = QuoteSnapshot(
        draft=normalized,
        submitted_at=submitted,
        material_gsm=float(material_gsm),
        material_price_cny_per_m2=float(material_price_cny_per_m2),
        webbing_price_cny_per_m=(
            float(webbing_price_cny_per_m)
            if webbing_price_cny_per_m is not None
            else None
        ),
        webbing_g_per_m=(
            float(webbing_g_per_m) if webbing_g_per_m is not None else None
        ),
    )
    return QuotationReport(snapshot=snapshot, tiers=tuple(tiers))
