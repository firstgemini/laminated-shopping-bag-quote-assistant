from __future__ import annotations

from html import escape
from pathlib import Path
import hmac
import os

import streamlit as st

from quote_app.calculations import (
    CUTTING_COST_CNY,
    HANDLE_BODY,
    HANDLE_WEBBING,
    PCS_PER_CARTON,
    SEWING_COST_CNY,
    QuoteValidationError,
)
from quote_app.quotation import (
    MAX_QUANTITY_TIERS,
    AddonItem,
    QuoteDraft,
    QuotationReport,
    build_quotation_report,
    normalize_draft,
)
from quote_app.reports import (
    ReportGenerationError,
    generate_customer_pdf,
    generate_internal_pdf,
)
from quote_app.repository import (
    PriceData,
    PriceDatabaseError,
    ensure_runtime_database,
    install_price_database,
    load_price_database,
)
from quote_app.settings import (
    AppSettings,
    load_settings,
    save_company_name,
    save_exchange_rate,
    save_supplier_contact,
)


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("QUOTE_DATA_DIR", ROOT / "data"))
SEED_DATABASE = ROOT / "price_database.xlsx"
PRICE_DATABASE = DATA_DIR / "price_database.xlsx"
SETTINGS_FILE = DATA_DIR / "app_settings.json"
BACKUP_DIR = DATA_DIR / "backups"

MATERIAL_HANDLE_WIDTHS = [2.2, 2.5, 3.0, 3.2, 3.5, 3.8, 4.0, 4.5]
SPECIAL_WEBBING_STYLE = "特殊织带（手填价格）"
SPECIAL_WEBBING_ESTIMATED_G_PER_M = 20.0


st.set_page_config(
    page_title="开口包报价精灵",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: light;
        --ft-paper: #fff1e5;
        --ft-surface: #fffaf5;
        --ft-ink: #33302e;
        --ft-claret: #990f3d;
        --ft-teal: #0d7680;
        --ft-border: #c9beb5;
        --ft-muted: #6f6863;
    }
    html, body, .stApp {
        background: var(--ft-paper);
        color: var(--ft-ink);
        font-family: "Noto Sans SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }
    header[data-testid="stHeader"] { display: none; }
    .block-container {
        max-width: 1180px;
        padding-top: 1.35rem;
        padding-bottom: 3rem;
    }
    h1, h2, h3 {
        color: var(--ft-ink);
        font-family: "Noto Serif SC", "Songti SC", SimSun, Georgia, serif !important;
        letter-spacing: 0 !important;
    }
    h1 { font-size: 2rem !important; margin-bottom: 0.15rem !important; }
    h2 { font-size: 1.22rem !important; margin-top: 1.25rem !important; }
    h3 { font-size: 1rem !important; }
    p, label, button, input, textarea { letter-spacing: 0 !important; }
    div[data-testid="stAlert"] {
        border: 1px solid var(--ft-border);
        border-radius: 4px;
        overflow-wrap: anywhere;
    }
    div[data-testid="stExpander"] {
        background: var(--ft-surface);
        border-color: var(--ft-border);
        border-radius: 4px;
    }
    div[data-baseweb="input"], div[data-baseweb="select"] > div,
    textarea, div[data-testid="stFileUploaderDropzone"] {
        background: var(--ft-surface) !important;
    }
    .status-line {
        display: flex;
        gap: 0.55rem;
        flex-wrap: wrap;
        color: var(--ft-muted);
        font-size: 0.86rem;
        margin: 0.15rem 0 1rem;
    }
    .status-line span {
        border-left: 3px solid var(--ft-teal);
        padding-left: 0.45rem;
        overflow-wrap: anywhere;
    }
    .section-note {
        color: var(--ft-muted);
        font-size: 0.86rem;
        margin: -0.35rem 0 0.75rem;
    }
    .record-stack { display: grid; gap: 0.65rem; margin: 0.45rem 0 1rem; }
    .record-block {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 0;
        background: var(--ft-surface);
        border: 1px solid var(--ft-border);
        border-left: 4px solid var(--ft-claret);
        border-radius: 4px;
        overflow: hidden;
    }
    .record-field {
        min-width: 0;
        padding: 0.68rem 0.72rem;
        border-right: 1px solid var(--ft-border);
        border-bottom: 1px solid var(--ft-border);
        overflow-wrap: anywhere;
    }
    .record-label {
        display: block;
        color: var(--ft-muted);
        font-size: 0.72rem;
        margin-bottom: 0.18rem;
    }
    .record-value {
        display: block;
        color: var(--ft-ink);
        font-size: 0.96rem;
        font-weight: 500;
    }
    .detail-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.55rem;
        margin: 0.55rem 0 1rem;
    }
    .detail-item {
        min-width: 0;
        background: var(--ft-surface);
        border-top: 2px solid var(--ft-teal);
        padding: 0.65rem 0.7rem;
        overflow-wrap: anywhere;
    }
    [role="tablist"] { gap: 0.25rem; flex-wrap: wrap; }
    [role="tab"] { white-space: nowrap; }
    div.stButton > button, div.stDownloadButton > button,
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        min-height: 42px;
        border-radius: 3px;
    }
    div.stButton > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background: var(--ft-claret);
        border-color: var(--ft-claret);
    }
    hr { border-color: var(--ft-border) !important; }
    @media (max-width: 700px) {
        .block-container { padding: 0.85rem 0.75rem 2rem; }
        h1 { font-size: 1.7rem !important; }
        [data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 0.65rem !important;
        }
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 0 !important;
        }
        .record-block { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        div.stButton > button, div.stDownloadButton > button,
        button[data-testid="stBaseButton-primaryFormSubmit"] { width: 100%; }
        .status-line { display: grid; grid-template-columns: 1fr; gap: 0.35rem; }
    }
    @media (max-width: 350px) {
        .record-block, .detail-grid { grid-template-columns: 1fr; }
        .block-container { padding-left: 0.55rem; padding-right: 0.55rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _read_secret(section: str, key: str, env_name: str, default: str) -> str:
    if os.environ.get(env_name):
        return os.environ[env_name]
    try:
        section_values = st.secrets.get(section, {})
        value = section_values.get(key)
        if value:
            return str(value)
    except (FileNotFoundError, KeyError, AttributeError):
        pass
    return default


def _credentials() -> tuple[str, str, bool]:
    user_password = _read_secret("passwords", "user", "APP_USER_PASSWORD", "quote")
    admin_password = _read_secret(
        "passwords", "admin", "APP_ADMIN_PASSWORD", "admin"
    )
    using_defaults = user_password == "quote" or admin_password == "admin"
    return user_password, admin_password, using_defaults


def _authenticate() -> str:
    if st.session_state.get("authenticated"):
        return str(st.session_state.get("role", "user"))

    st.title("开口包报价精灵")
    st.caption("Laminated Shopping Bag Quotation")
    with st.form("login_form", clear_on_submit=False):
        password = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("登录", use_container_width=True)

    if submitted:
        user_password, admin_password, _ = _credentials()
        if hmac.compare_digest(password, admin_password):
            st.session_state.authenticated = True
            st.session_state.role = "admin"
            st.rerun()
        if hmac.compare_digest(password, user_password):
            st.session_state.authenticated = True
            st.session_state.role = "user"
            st.rerun()
        st.error("密码不正确。")
    st.stop()


@st.cache_data(show_spinner=False)
def _cached_database(path: str, modified_ns: int, size: int) -> PriceData:
    del modified_ns, size
    return load_price_database(Path(path))


def _load_runtime_database() -> PriceData:
    ensure_runtime_database(SEED_DATABASE, PRICE_DATABASE)
    stat = PRICE_DATABASE.stat()
    return _cached_database(str(PRICE_DATABASE), stat.st_mtime_ns, stat.st_size)


def _select_with_valid_state(
    label: str,
    options: list,
    *,
    key: str,
    format_func=None,
):
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    widget_options = {"key": key}
    if format_func is not None:
        widget_options["format_func"] = format_func
    return st.selectbox(label, options, **widget_options)


def _initialize_dynamic_rows() -> None:
    if "quantity_row_ids" not in st.session_state:
        st.session_state.quantity_row_ids = [1]
        st.session_state.next_quantity_id = 2
        st.session_state["quantity_1"] = 10_000
    if "addon_row_ids" not in st.session_state:
        st.session_state.addon_row_ids = []
        st.session_state.next_addon_id = 1


def _add_quantity_row() -> None:
    if len(st.session_state.quantity_row_ids) >= MAX_QUANTITY_TIERS:
        return
    row_id = st.session_state.next_quantity_id
    st.session_state.next_quantity_id += 1
    st.session_state.quantity_row_ids.append(row_id)
    existing = [
        int(st.session_state.get(f"quantity_{item}", 0))
        for item in st.session_state.quantity_row_ids[:-1]
    ]
    st.session_state[f"quantity_{row_id}"] = max(existing, default=0) + 5_000


def _remove_quantity_row(row_id: int) -> None:
    if len(st.session_state.quantity_row_ids) <= 1:
        return
    st.session_state.quantity_row_ids.remove(row_id)
    st.session_state.pop(f"quantity_{row_id}", None)


def _add_addon_row() -> None:
    row_id = st.session_state.next_addon_id
    st.session_state.next_addon_id += 1
    st.session_state.addon_row_ids.append(row_id)
    st.session_state[f"addon_internal_{row_id}"] = ""
    st.session_state[f"addon_english_{row_id}"] = ""
    st.session_state[f"addon_cost_{row_id}"] = 0.0


def _remove_addon_row(row_id: int) -> None:
    st.session_state.addon_row_ids.remove(row_id)
    for prefix in ("addon_internal", "addon_english", "addon_cost"):
        st.session_state.pop(f"{prefix}_{row_id}", None)


def _render_header(database: PriceData, settings: AppSettings, role: str) -> None:
    title_col, action_col = st.columns([5, 1])
    with title_col:
        st.title("开口包报价精灵")
        local_time = database.modified_at.astimezone().strftime("%Y-%m-%d %H:%M")
        company = settings.company_name_en or "未设置英文公司名"
        st.markdown(
            (
                '<div class="status-line">'
                f"<span>价格库 {escape(local_time)}</span>"
                f"<span>汇率 {settings.exchange_rate:g}</span>"
                f"<span>{'管理员' if role == 'admin' else '业务员'}</span>"
                f"<span>{escape(company)}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with action_col:
        if st.button("退出", use_container_width=True, icon=":material/logout:"):
            st.session_state.clear()
            st.rerun()


def _render_quantity_rows() -> tuple[int, ...]:
    st.subheader("数量阶梯")
    st.markdown(
        '<div class="section-note">每个数量必须是100的整数倍，最多10个。</div>',
        unsafe_allow_html=True,
    )
    quantities: list[int] = []
    for index, row_id in enumerate(list(st.session_state.quantity_row_ids), start=1):
        input_col, remove_col = st.columns([6, 1], vertical_alignment="bottom")
        with input_col:
            quantity = st.number_input(
                f"数量 {index}（个）",
                min_value=PCS_PER_CARTON,
                max_value=10_000_000,
                step=PCS_PER_CARTON,
                key=f"quantity_{row_id}",
            )
            quantities.append(int(quantity))
        with remove_col:
            if st.button(
                "删除",
                key=f"remove_quantity_{row_id}",
                icon=":material/remove:",
                help=f"删除数量 {index}",
                disabled=len(st.session_state.quantity_row_ids) <= 1,
                use_container_width=True,
            ):
                _remove_quantity_row(row_id)
                st.rerun()

    if st.button(
        "增加数量",
        icon=":material/add:",
        disabled=len(st.session_state.quantity_row_ids) >= MAX_QUANTITY_TIERS,
        use_container_width=True,
    ):
        _add_quantity_row()
        st.rerun()
    return tuple(quantities)


def _render_addon_rows() -> tuple[AddonItem, ...]:
    st.subheader("附加项目")
    st.markdown(
        '<div class="section-note">按人民币元/个录入；不添加时费用为0。客户PDF仅显示英文名称。</div>',
        unsafe_allow_html=True,
    )
    addons: list[AddonItem] = []
    for index, row_id in enumerate(list(st.session_state.addon_row_ids), start=1):
        internal_col, english_col, cost_col, remove_col = st.columns(
            [2.2, 2.2, 1.2, 0.9], vertical_alignment="bottom"
        )
        with internal_col:
            internal_name = st.text_input(
                f"内部名称 {index}", key=f"addon_internal_{row_id}"
            )
        with english_col:
            english_name = st.text_input(
                f"英文名称 {index}（可选）", key=f"addon_english_{row_id}"
            )
        with cost_col:
            unit_cost = st.number_input(
                f"单价 {index}",
                min_value=0.0,
                max_value=1_000.0,
                step=0.01,
                format="%.4f",
                key=f"addon_cost_{row_id}",
            )
        with remove_col:
            if st.button(
                "删除",
                key=f"remove_addon_{row_id}",
                icon=":material/delete:",
                help=f"删除附加项目 {index}",
                use_container_width=True,
            ):
                _remove_addon_row(row_id)
                st.rerun()
        addons.append(
            AddonItem(
                internal_name=internal_name,
                english_name=english_name,
                unit_cost_cny=float(unit_cost),
            )
        )

    if st.button("增加附加项目", icon=":material/add:", use_container_width=True):
        _add_addon_row()
        st.rerun()
    return tuple(addons)


def _render_record_stack(records: list[list[tuple[str, str]]]) -> None:
    blocks: list[str] = ['<div class="record-stack">']
    for record in records:
        blocks.append('<section class="record-block">')
        for label, value in record:
            blocks.append(
                '<div class="record-field">'
                f'<span class="record-label">{escape(label)}</span>'
                f'<span class="record-value">{escape(value)}</span>'
                "</div>"
            )
        blocks.append("</section>")
    blocks.append("</div>")
    st.markdown("".join(blocks), unsafe_allow_html=True)


def _render_detail_grid(items: list[tuple[str, str]]) -> None:
    cells = ['<div class="detail-grid">']
    for label, value in items:
        cells.append(
            '<div class="detail-item">'
            f'<span class="record-label">{escape(label)}</span>'
            f'<span class="record-value">{escape(value)}</span>'
            "</div>"
        )
    cells.append("</div>")
    st.markdown("".join(cells), unsafe_allow_html=True)


def _render_results(report: QuotationReport, role: str) -> None:
    st.divider()
    st.subheader("数量阶梯报价")
    tier_records: list[list[tuple[str, str]]] = []
    for tier in report.tiers:
        result = tier.result
        tier_records.append(
            [
                ("数量", f"{tier.quantity:,}"),
                ("EXW 人民币", f"¥ {result.exw_cny:.3f}"),
                ("EXW 美元", f"$ {result.exw_usd:.3f}"),
                ("箱数", f"{result.carton_count:,}"),
                ("总CBM", f"{result.total_cbm:.3f}"),
                ("运输", result.freight.mode),
                ("本地总费", f"¥ {result.freight.total_cost_cny:,.0f}"),
                ("FOB 人民币", f"¥ {result.fob_cny:.3f}"),
                ("FOB 美元", f"$ {result.fob_usd:.3f}"),
            ]
        )
    _render_record_stack(tier_records)

    quantities = [tier.quantity for tier in report.tiers]
    selected_quantity = _select_with_valid_state(
        "查看阶梯详情",
        quantities,
        key="detail_quantity",
        format_func=lambda value: f"{value:,} 个",
    )
    tier = next(item for item in report.tiers if item.quantity == selected_quantity)
    result = tier.result
    draft = report.snapshot.draft

    def render_packing() -> None:
        _render_detail_grid(
            [
                ("装箱数", "100个/箱"),
                ("总箱数", f"{result.carton_count:,}箱"),
                (
                    "外箱尺寸",
                    f"{result.carton_length_cm:g} x {result.carton_width_cm:g} x {result.carton_height_cm:g} cm",
                ),
                ("NW/箱", f"{result.carton_nw_kg:.2f}kg"),
                ("GW/箱", f"{result.carton_gw_kg:.2f}kg"),
                ("总NW", f"{result.total_nw_kg:,.2f}kg"),
                ("总GW", f"{result.total_gw_kg:,.2f}kg"),
                ("总CBM", f"{result.total_cbm:.3f}"),
            ]
        )
        st.info("预计装箱数据用于询价和FOB费用估算，最终以大货实测箱规为准。")

    if role in {"admin", "user"}:
        cost_tab, packing_tab, parameter_tab = st.tabs(["成本", "装箱", "参数"])
        with cost_tab:
            cost_items = [
                ("袋身面料", f"¥ {result.body_cost_cny:.4f}/个"),
                ("包边", f"¥ {result.binding_cost_cny:.4f}/个"),
                ("手提", f"¥ {result.handle_cost_cny:.4f}/个"),
                ("车缝", f"¥ {SEWING_COST_CNY:.4f}/个"),
                ("分切", f"¥ {CUTTING_COST_CNY:.4f}/个"),
                ("纸箱分摊", f"¥ {result.carton_share_cny:.4f}/个"),
                ("其它损耗", f"¥ {result.loss_cny:.4f}/个"),
                ("工厂利润", f"¥ {result.profit_cny:.4f}/个"),
            ]
            for addon in draft.addons:
                cost_items.append(
                    (f"附加：{addon.internal_name}", f"¥ {addon.unit_cost_cny:.4f}/个")
                )
            _render_detail_grid(cost_items)
            st.caption(
                f"单色版费：$ {result.plate_fee_usd_per_color:.2f} ｜ "
                f"FOB本地费分摊：¥ {result.freight_per_bag_cny:.4f}/个"
            )
        with packing_tab:
            render_packing()
        with parameter_tab:
            _render_detail_grid(
                [
                    ("排料尺寸", f"{result.layout_width_cm:g} x {result.layout_height_cm:g}cm"),
                    ("袋身面积", f"{result.fabric_area_m2:.4f}m²"),
                    ("包边长度", f"{result.binding_length_cm:g}cm"),
                    ("包边面积", f"{result.binding_area_m2:.4f}m²"),
                    ("手提面积", f"{result.handle_area_m2:.4f}m²"),
                    ("材料单价", f"¥ {result.material_price_cny_per_m2:.3f}/m²"),
                    (
                        "织带单价",
                        f"¥ {result.webbing_price_cny_per_m:.3f}/m"
                        if result.webbing_price_cny_per_m is not None
                        else "不适用",
                    ),
                    ("单箱体积", f"{result.carton_cbm:.4f}CBM"),
                    ("单只净重", f"{result.bag_net_weight_kg:.4f}kg"),
                ]
            )
    else:
        st.subheader("预计装箱信息")
        render_packing()

    st.subheader("下载")
    date_code = report.snapshot.submitted_at.strftime("%Y%m%d")
    if role in {"admin", "user"}:
        internal_col, customer_col = st.columns(2)
    else:
        customer_col = st.container()
        internal_col = None
    if internal_col is not None:
        with internal_col:
            try:
                internal_pdf = generate_internal_pdf(report)
                st.download_button(
                    "下载内部核价单 PDF",
                    data=internal_pdf,
                    file_name=f"internal_costing_{date_code}.pdf",
                    mime="application/pdf",
                    icon=":material/download:",
                    use_container_width=True,
                )
            except ReportGenerationError as exc:
                st.error(f"内部核价单生成失败：{exc}")
    with customer_col:
        try:
            customer_pdf = generate_customer_pdf(report)
            st.download_button(
                "Download Customer Quotation PDF",
                data=customer_pdf,
                file_name=f"customer_quotation_{date_code}.pdf",
                mime="application/pdf",
                icon=":material/download:",
                use_container_width=True,
            )
        except ReportGenerationError as exc:
            st.error(f"客户英文报价单生成失败：{exc}")


def _render_quote(database: PriceData, settings: AppSettings, role: str) -> None:
    _initialize_dynamic_rows()
    st.subheader("产品参数")
    size_cols = st.columns(3)
    with size_cols[0]:
        width_cm = st.number_input(
            "袋宽 W（cm）", min_value=1.0, max_value=300.0, value=40.0, step=0.5
        )
    with size_cols[1]:
        height_cm = st.number_input(
            "袋高 H（cm）", min_value=1.0, max_value=300.0, value=35.0, step=0.5
        )
    with size_cols[2]:
        gusset_cm = st.number_input(
            "侧宽 G（cm）", min_value=1.0, max_value=200.0, value=12.0, step=0.5
        )

    handle_col, customer_col = st.columns(2)
    with handle_col:
        handle_length_cm = st.number_input(
            "单条手提长度（cm）",
            min_value=1.0,
            max_value=500.0,
            value=70.0,
            step=1.0,
        )
    with customer_col:
        customer_info = st.text_area(
            "客户信息（可选）",
            placeholder="Customer name, company, email and address in English",
            height=104,
        )

    supplier_contact_en = settings.supplier_contact_en
    if role == "admin":
        with st.expander("本次PDF发件人信息（可选覆盖）"):
            st.caption("留空时使用管理员设置的默认英文联系信息；此处内容只用于客户PDF。")
            supplier_contact_override = st.text_area(
                "英文发件人信息",
                value="",
                placeholder=settings.supplier_contact_en,
                height=150,
                key="supplier_contact_override",
            )
        supplier_contact_en = (
            supplier_contact_override.strip() or settings.supplier_contact_en
        )

    material_cols = st.columns(2)
    with material_cols[0]:
        material = _select_with_valid_state(
            "袋身材料", database.materials(), key="material"
        )
    gsm_options = database.gsm_options(material)
    with material_cols[1]:
        gsm_label = _select_with_valid_state(
            "规格克重（GSM）", gsm_options, key="gsm_label"
        )

    st.subheader("手提")
    handle_type = st.radio(
        "手提类型",
        [HANDLE_BODY, HANDLE_WEBBING],
        horizontal=True,
        label_visibility="collapsed",
    )
    webbing_style = None
    if handle_type == HANDLE_BODY:
        handle_width_cm = _select_with_valid_state(
            "本料手提成品宽度",
            MATERIAL_HANDLE_WIDTHS,
            key="body_handle_width",
            format_func=lambda value: f"{value:g} cm",
        )
        webbing_record = None
    else:
        webbing_cols = st.columns(2)
        with webbing_cols[0]:
            webbing_style = _select_with_valid_state(
                "织带样式",
                [*database.webbing_styles(), SPECIAL_WEBBING_STYLE],
                key="webbing_style",
            )
        if webbing_style == SPECIAL_WEBBING_STYLE:
            with webbing_cols[1]:
                handle_width_cm = st.number_input(
                    "特殊织带宽度（cm）",
                    min_value=0.1,
                    max_value=20.0,
                    value=2.5,
                    step=0.1,
                )
            special_webbing_price = st.number_input(
                "特殊织带单价（人民币元/米）",
                min_value=0.0001,
                max_value=100.0,
                value=0.50,
                step=0.01,
                format="%.4f",
            )
            st.caption("成本按两条手提长度并加5%裁剪损耗；装箱重量按20g/米保守估算。")
            webbing_record = {
                "price_per_m": float(special_webbing_price),
                "grams_per_m": SPECIAL_WEBBING_ESTIMATED_G_PER_M,
            }
        else:
            widths = database.webbing_widths(webbing_style)
            with webbing_cols[1]:
                handle_width_cm = _select_with_valid_state(
                    "织带宽度",
                    widths,
                    key="webbing_width",
                    format_func=lambda value: f"{value:g} cm",
                )
            webbing_record = database.webbing_record(webbing_style, handle_width_cm)

    quantities = _render_quantity_rows()
    addons = _render_addon_rows()
    material_record = database.material_record(material, gsm_label)
    draft = QuoteDraft(
        width_cm=float(width_cm),
        height_cm=float(height_cm),
        gusset_cm=float(gusset_cm),
        handle_length_cm=float(handle_length_cm),
        quantities=quantities,
        exchange_rate=float(settings.exchange_rate),
        material=material,
        gsm_label=gsm_label,
        handle_type=handle_type,
        handle_width_cm=float(handle_width_cm),
        webbing_style=webbing_style,
        customer_info=customer_info,
        addons=addons,
        database_fingerprint=database.fingerprint,
        company_name_en=settings.company_name_en,
        supplier_contact_en=supplier_contact_en,
    )

    submitted = st.button(
        "提交核价",
        type="primary",
        icon=":material/calculate:",
        use_container_width=True,
    )
    if submitted:
        try:
            report = build_quotation_report(
                draft,
                material_gsm=float(material_record["gsm"]),
                material_price_cny_per_m2=float(material_record["price_per_m2"]),
                webbing_price_cny_per_m=(
                    float(webbing_record["price_per_m"])
                    if webbing_record is not None
                    else None
                ),
                webbing_g_per_m=(
                    float(webbing_record["grams_per_m"])
                    if webbing_record is not None
                    else None
                ),
            )
            st.session_state.quotation_report = report
        except (QuoteValidationError, PriceDatabaseError) as exc:
            st.error(str(exc))

    report: QuotationReport | None = st.session_state.get("quotation_report")
    if report is None:
        st.info("请选择参数并点击“提交核价”。")
        return
    if report.snapshot.draft != normalize_draft(draft):
        st.warning("参数已经修改，请重新提交核价。旧结果和下载已失效。")
        return
    _render_results(report, role)


def _render_settings(settings: AppSettings, role: str) -> None:
    st.subheader("全厂汇率")
    st.caption("保存后立即对所有新报价生效。")
    new_rate = st.number_input(
        "人民币兑美元报价汇率",
        min_value=0.0001,
        max_value=100.0,
        value=float(settings.exchange_rate),
        step=0.01,
        format="%.4f",
        key="exchange_rate_edit",
    )
    if st.button(
        "保存全厂汇率", type="primary", icon=":material/save:", use_container_width=True
    ):
        save_exchange_rate(SETTINGS_FILE, float(new_rate))
        st.session_state.flash_message = f"全厂汇率已更新为 {new_rate:g}。"
        st.rerun()

    if role == "admin":
        st.divider()
        st.subheader("客户PDF页眉")
        company_name = st.text_input(
            "英文公司名称",
            value=settings.company_name_en,
            placeholder="Example Bags Manufacturing Co., Ltd.",
        )
        if st.button(
            "保存英文公司名称",
            icon=":material/save:",
            use_container_width=True,
        ):
            save_company_name(SETTINGS_FILE, company_name)
            st.session_state.flash_message = "英文公司名称已保存。"
            st.rerun()

        supplier_contact = st.text_area(
            "默认英文发件人信息",
            value=settings.supplier_contact_en,
            height=190,
        )
        if st.button(
            "保存默认发件人信息",
            icon=":material/save:",
            use_container_width=True,
        ):
            save_supplier_contact(SETTINGS_FILE, supplier_contact)
            st.session_state.flash_message = "默认英文发件人信息已保存。"
            st.rerun()


def _render_admin(database: PriceData) -> None:
    st.subheader("价格库管理")
    st.caption("上传前校验；成功后备份旧版本并立即切换。")
    uploaded = st.file_uploader(
        "上传 price_database.xlsx", type=["xlsx"], accept_multiple_files=False
    )
    if st.button(
        "校验并更新价格库",
        type="primary",
        icon=":material/upload_file:",
        disabled=uploaded is None,
        use_container_width=True,
    ):
        try:
            installed = install_price_database(
                uploaded.getvalue(),
                target_path=PRICE_DATABASE,
                backup_dir=BACKUP_DIR,
            )
            _cached_database.clear()
            st.session_state.flash_message = (
                f"价格库更新成功，版本 {installed.fingerprint[:8]}。"
            )
            st.rerun()
        except PriceDatabaseError as exc:
            st.error(str(exc))

    st.download_button(
        "下载当前价格库",
        data=PRICE_DATABASE.read_bytes(),
        file_name="price_database.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
        use_container_width=True,
    )
    _render_detail_grid(
        [
            ("当前版本", database.fingerprint[:12]),
            ("材料记录", str(len(database.body))),
            ("织带记录", str(len(database.webbing))),
        ]
    )

    if database.warnings:
        st.warning("\n\n".join(database.warnings))
    else:
        st.success("当前价格库校验通过。")

    backups = sorted(BACKUP_DIR.glob("price_database_*.xlsx"), reverse=True)
    if backups:
        with st.expander(f"备份版本（{len(backups)}）"):
            for backup in backups:
                st.text(backup.name)


def main() -> None:
    role = _authenticate()
    user_password, admin_password, using_defaults = _credentials()
    del user_password, admin_password

    try:
        database = _load_runtime_database()
    except PriceDatabaseError as exc:
        st.error(str(exc))
        st.stop()

    settings_result = load_settings(SETTINGS_FILE)
    settings = settings_result.settings
    _render_header(database, settings, role)

    flash_message = st.session_state.pop("flash_message", None)
    if flash_message:
        st.success(flash_message)
    if settings_result.warning:
        st.warning(settings_result.warning)
    if using_defaults:
        st.warning("当前使用开发默认密码，请在云端部署前配置业务密码和管理员密码。")
    if database.warnings:
        st.warning(f"价格库有 {len(database.warnings)} 条异常提醒，请管理员核实。")

    tab_names = ["核价"]
    if role == "admin":
        tab_names.extend(["设置", "价格库"])
    tabs = st.tabs(tab_names)
    with tabs[0]:
        _render_quote(database, settings, role)
    if role == "admin":
        with tabs[1]:
            _render_settings(settings, role)
        with tabs[2]:
            _render_admin(database)


if __name__ == "__main__":
    main()
