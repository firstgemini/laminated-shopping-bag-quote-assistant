from __future__ import annotations

from dataclasses import dataclass
from math import floor


PCS_PER_CARTON = 100
MOUTH_FOLD_CM = 3.0
BINDING_WIDTH_CM = 2.5
WEBBING_WASTE_FACTOR = 1.05
SEWING_COST_CNY = 0.50
CUTTING_COST_CNY = 0.05
CARTON_PRICE_CNY_PER_M2 = 2.86
CARTON_BOARD_KG_PER_M2 = 0.50

HANDLE_BODY = "本料手提"
HANDLE_WEBBING = "PP织带"

WOVEN_MATERIALS = {
    "PP编织覆膜二等材料",
    "编织双面OPP覆膜材料",
}
NONWOVEN_MATERIALS = {
    "无纺布覆膜一等材料",
    "无纺布覆膜二等材料",
    "无纺布双面OPP覆膜材料",
}
PET_MATERIALS = {"PET材料（丽新布覆膜）"}


class QuoteValidationError(ValueError):
    """Raised when a quotation input violates a locked business rule."""


@dataclass(frozen=True)
class QuoteInputs:
    width_cm: float
    height_cm: float
    gusset_cm: float
    handle_length_cm: float
    quantity: int
    exchange_rate: float
    material: str
    gsm_label: str
    handle_type: str
    handle_width_cm: float
    webbing_style: str | None = None


@dataclass(frozen=True)
class FreightComponent:
    mode: str
    cbm: float
    cost_cny: float
    count: int = 1


@dataclass(frozen=True)
class FreightResult:
    mode: str
    total_cost_cny: float
    components: tuple[FreightComponent, ...]


@dataclass(frozen=True)
class QuoteResult:
    exw_cny: float
    exw_usd: float
    fob_cny: float
    fob_usd: float
    plate_fee_usd_per_color: float
    freight: FreightResult
    freight_per_bag_cny: float
    carton_count: int
    carton_length_cm: float
    carton_width_cm: float
    carton_height_cm: float
    carton_area_m2: float
    carton_cost_cny: float
    carton_cbm: float
    total_cbm: float
    bag_net_weight_kg: float
    carton_nw_kg: float
    carton_gw_kg: float
    total_nw_kg: float
    total_gw_kg: float
    layout_width_cm: float
    layout_height_cm: float
    fabric_area_m2: float
    binding_length_cm: float
    binding_area_m2: float
    handle_area_m2: float
    body_cost_cny: float
    binding_cost_cny: float
    handle_cost_cny: float
    additional_cost_cny: float
    carton_share_cny: float
    loss_cny: float
    profit_cny: float
    material_price_cny_per_m2: float
    webbing_price_cny_per_m: float | None


def validate_inputs(inputs: QuoteInputs) -> None:
    dimensions = {
        "袋宽": inputs.width_cm,
        "袋高": inputs.height_cm,
        "侧宽": inputs.gusset_cm,
        "手提长度": inputs.handle_length_cm,
        "手提宽度": inputs.handle_width_cm,
    }
    for label, value in dimensions.items():
        if value <= 0:
            raise QuoteValidationError(f"{label}必须大于0。")

    if inputs.quantity < PCS_PER_CARTON:
        raise QuoteValidationError("订单数量不能少于100个。")
    if inputs.quantity % PCS_PER_CARTON != 0:
        raise QuoteValidationError("订单数量必须是100的整数倍。")
    if inputs.exchange_rate <= 0:
        raise QuoteValidationError("汇率必须大于0。")
    if inputs.handle_type not in {HANDLE_BODY, HANDLE_WEBBING}:
        raise QuoteValidationError("手提类型无效。")
    if inputs.handle_type == HANDLE_WEBBING and not inputs.webbing_style:
        raise QuoteValidationError("请选择织带样式。")


def quantity_loss_cny(quantity: int) -> float:
    if quantity <= 2_000:
        return 0.30
    if quantity <= 3_000:
        return 0.25
    if quantity <= 5_000:
        return 0.20
    if quantity <= 9_999:
        return 0.15
    return 0.10


def quantity_profit_cny(quantity: int) -> float:
    if quantity <= 1_000:
        return 0.40
    if quantity <= 2_000:
        return 0.35
    if quantity <= 3_000:
        return 0.30
    if quantity <= 5_000:
        return 0.25
    if quantity <= 25_000:
        return 0.20
    if quantity <= 50_000:
        return 0.15
    return 0.10


def carton_base_height_cm(material: str) -> float:
    if material in WOVEN_MATERIALS:
        return 26.0
    if material in NONWOVEN_MATERIALS:
        return 30.0
    if material in PET_MATERIALS:
        return 35.0
    raise QuoteValidationError(f"材料“{material}”没有配置外箱基础高度。")


def carton_height_cm(material: str, bag_height_cm: float) -> float:
    base = carton_base_height_cm(material)
    if bag_height_cm < 30:
        return base + 2
    if bag_height_cm > 38:
        return base - 3
    return base


def _single_shipment_freight(cbm: float) -> FreightComponent:
    if cbm < 15:
        return FreightComponent("LCL拼箱", cbm, 1_390 + max(3.0, cbm) * 75)
    if cbm <= 28:
        return FreightComponent("20GP", cbm, 6_000)
    if cbm <= 68:
        return FreightComponent("40HQ", cbm, 9_000)
    if cbm <= 78:
        return FreightComponent("45HQ", cbm, 10_000)
    raise QuoteValidationError("单票运费计算收到超过78 CBM的体积。")


def calculate_freight(total_cbm: float) -> FreightResult:
    if total_cbm <= 0:
        raise QuoteValidationError("总体积必须大于0。")

    if total_cbm <= 78:
        component = _single_shipment_freight(total_cbm)
        return FreightResult(component.mode, component.cost_cny, (component,))

    full_40hq = floor((total_cbm + 1e-9) / 68)
    remainder = max(0.0, total_cbm - full_40hq * 68)
    components: list[FreightComponent] = [
        FreightComponent("40HQ", 68.0, 9_000 * full_40hq, full_40hq)
    ]
    if remainder > 1e-9:
        components.append(_single_shipment_freight(remainder))

    total_cost = sum(component.cost_cny for component in components)
    labels = [
        f"{component.count}×{component.mode}"
        if component.count > 1
        else component.mode
        for component in components
    ]
    return FreightResult(" + ".join(labels), total_cost, tuple(components))


def calculate_quote(
    inputs: QuoteInputs,
    *,
    material_price_cny_per_m2: float,
    material_gsm: float,
    webbing_price_cny_per_m: float | None = None,
    webbing_g_per_m: float | None = None,
    additional_unit_cost_cny: float = 0.0,
) -> QuoteResult:
    validate_inputs(inputs)
    if material_price_cny_per_m2 <= 0 or material_gsm <= 0:
        raise QuoteValidationError("材料价格和克重必须大于0。")
    if additional_unit_cost_cny < 0:
        raise QuoteValidationError("附加项目单价不能为负数。")

    if inputs.handle_type == HANDLE_WEBBING:
        if not webbing_price_cny_per_m or webbing_price_cny_per_m <= 0:
            raise QuoteValidationError("织带每米价格无效。")
        if not webbing_g_per_m or webbing_g_per_m <= 0:
            raise QuoteValidationError("织带每米克重无效。")

    layout_width = inputs.width_cm + inputs.gusset_cm + 2
    layout_height = (
        (inputs.height_cm + MOUTH_FOLD_CM) * 2 + inputs.gusset_cm - 1
    )
    fabric_area = layout_width * layout_height / 10_000
    body_cost = fabric_area * material_price_cny_per_m2

    binding_length = inputs.height_cm * 4 + inputs.gusset_cm * 2 + 12
    binding_area = BINDING_WIDTH_CM * binding_length / 10_000
    binding_cost = binding_area * material_price_cny_per_m2

    handle_area = 0.0
    if inputs.handle_type == HANDLE_BODY:
        handle_area = (
            inputs.handle_width_cm
            * 2.4
            * inputs.handle_length_cm
            * 2
            / 10_000
        )
        handle_cost = handle_area * material_price_cny_per_m2
        handle_weight = handle_area * material_gsm / 1_000
    else:
        handle_length_m = inputs.handle_length_cm * 2 / 100
        handle_cost = (
            handle_length_m
            * float(webbing_price_cny_per_m)
            * WEBBING_WASTE_FACTOR
        )
        handle_weight = handle_length_m * float(webbing_g_per_m) / 1_000

    box_length = inputs.width_cm + 3
    box_width = inputs.height_cm + 4
    box_height = carton_height_cm(inputs.material, inputs.height_cm)
    carton_area = (
        (box_length + box_width + 5)
        * (box_width + box_height + 3)
        * 2
        / 10_000
    )
    carton_cost = carton_area * CARTON_PRICE_CNY_PER_M2
    carton_share = carton_cost / PCS_PER_CARTON

    loss = quantity_loss_cny(inputs.quantity)
    profit = quantity_profit_cny(inputs.quantity)
    exw_cny = (
        body_cost
        + binding_cost
        + handle_cost
        + additional_unit_cost_cny
        + SEWING_COST_CNY
        + CUTTING_COST_CNY
        + carton_share
        + loss
        + profit
    )
    exw_usd = exw_cny / inputs.exchange_rate

    bag_net_weight = (
        (fabric_area + binding_area) * material_gsm / 1_000 + handle_weight
    )
    carton_nw = bag_net_weight * PCS_PER_CARTON
    carton_gw = carton_nw + carton_area * CARTON_BOARD_KG_PER_M2
    carton_cbm = box_length * box_width * box_height / 1_000_000
    carton_count = inputs.quantity // PCS_PER_CARTON
    total_cbm = carton_count * carton_cbm
    total_nw = carton_nw * carton_count
    total_gw = carton_gw * carton_count

    freight = calculate_freight(total_cbm)
    freight_per_bag = freight.total_cost_cny / inputs.quantity
    fob_cny = exw_cny + freight_per_bag
    fob_usd = fob_cny / inputs.exchange_rate
    plate_fee = fabric_area * 1_000 / inputs.exchange_rate

    return QuoteResult(
        exw_cny=exw_cny,
        exw_usd=exw_usd,
        fob_cny=fob_cny,
        fob_usd=fob_usd,
        plate_fee_usd_per_color=plate_fee,
        freight=freight,
        freight_per_bag_cny=freight_per_bag,
        carton_count=carton_count,
        carton_length_cm=box_length,
        carton_width_cm=box_width,
        carton_height_cm=box_height,
        carton_area_m2=carton_area,
        carton_cost_cny=carton_cost,
        carton_cbm=carton_cbm,
        total_cbm=total_cbm,
        bag_net_weight_kg=bag_net_weight,
        carton_nw_kg=carton_nw,
        carton_gw_kg=carton_gw,
        total_nw_kg=total_nw,
        total_gw_kg=total_gw,
        layout_width_cm=layout_width,
        layout_height_cm=layout_height,
        fabric_area_m2=fabric_area,
        binding_length_cm=binding_length,
        binding_area_m2=binding_area,
        handle_area_m2=handle_area,
        body_cost_cny=body_cost,
        binding_cost_cny=binding_cost,
        handle_cost_cny=handle_cost,
        additional_cost_cny=additional_unit_cost_cny,
        carton_share_cny=carton_share,
        loss_cny=loss,
        profit_cny=profit,
        material_price_cny_per_m2=material_price_cny_per_m2,
        webbing_price_cny_per_m=webbing_price_cny_per_m,
    )
