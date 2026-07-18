from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import shutil
import threading
import uuid

import pandas as pd


BODY_SHEET = "袋身材料"
WEBBING_SHEET = "织带材料"
BODY_REQUIRED_COLUMNS = ("材料分类", "规格克重", "每平方米单价(元)")
WEBBING_REQUIRED_COLUMNS = (
    "样式",
    "宽度（公分）",
    "每米克重",
    "每米单价（元）",
)
MATERIAL_PRIORITY = (
    "PET材料（丽新布覆膜）",
    "无纺布覆膜二等材料",
    "PP编织覆膜二等材料",
    "无纺布覆膜一等材料",
    "编织双面OPP覆膜材料",
    "无纺布双面OPP覆膜材料",
)
MAX_BACKUPS = 10

_INSTALL_LOCK = threading.Lock()


class PriceDatabaseError(ValueError):
    """Raised when a price workbook cannot be trusted for quotations."""


@dataclass(frozen=True)
class PriceData:
    body: pd.DataFrame
    webbing: pd.DataFrame
    warnings: tuple[str, ...]
    modified_at: datetime
    fingerprint: str

    def materials(self) -> list[str]:
        present = set(self.body["material"].tolist())
        ordered = [name for name in MATERIAL_PRIORITY if name in present]
        ordered.extend(sorted(present.difference(ordered)))
        return ordered

    def gsm_options(self, material: str) -> list[str]:
        rows = self.body[self.body["material"] == material]
        return rows.sort_values("gsm")["gsm_label"].tolist()

    def material_record(self, material: str, gsm_label: str) -> pd.Series:
        rows = self.body[
            (self.body["material"] == material)
            & (self.body["gsm_label"] == gsm_label)
        ]
        if len(rows) != 1:
            raise PriceDatabaseError(
                f"无法唯一匹配袋身材料：{material} / {gsm_label}。"
            )
        return rows.iloc[0]

    def webbing_styles(self) -> list[str]:
        return sorted(self.webbing["style"].unique().tolist())

    def webbing_widths(self, style: str) -> list[float]:
        rows = self.webbing[self.webbing["style"] == style]
        return sorted(rows["width_cm"].astype(float).tolist())

    def webbing_record(self, style: str, width_cm: float) -> pd.Series:
        rows = self.webbing[
            (self.webbing["style"] == style)
            & (self.webbing["width_cm"].sub(width_cm).abs() < 1e-9)
        ]
        if len(rows) != 1:
            raise PriceDatabaseError(
                f"无法唯一匹配PP织带：{style} / {width_cm:g}cm。"
            )
        return rows.iloc[0]


def _clean_columns(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.dropna(how="all").copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    return cleaned


def _require_columns(
    frame: pd.DataFrame, required: tuple[str, ...], sheet_name: str
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise PriceDatabaseError(
            f"工作表“{sheet_name}”缺少字段：{', '.join(missing)}。"
        )


def _numeric(series: pd.Series, field: str, sheet_name: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        rows = (values[values.isna()].index + 2).tolist()
        raise PriceDatabaseError(
            f"工作表“{sheet_name}”的“{field}”存在非数字，Excel行：{rows}。"
        )
    if (values <= 0).any():
        rows = (values[values <= 0].index + 2).tolist()
        raise PriceDatabaseError(
            f"工作表“{sheet_name}”的“{field}”必须大于0，Excel行：{rows}。"
        )
    return values.astype(float)


def validate_frames(
    frames: dict[str, pd.DataFrame], *, modified_at: datetime, fingerprint: str
) -> PriceData:
    missing_sheets = [
        sheet for sheet in (BODY_SHEET, WEBBING_SHEET) if sheet not in frames
    ]
    if missing_sheets:
        raise PriceDatabaseError(
            f"Excel缺少工作表：{', '.join(missing_sheets)}。"
        )

    warnings: list[str] = []
    body_raw = _clean_columns(frames[BODY_SHEET])
    _require_columns(body_raw, BODY_REQUIRED_COLUMNS, BODY_SHEET)
    body = body_raw.loc[:, BODY_REQUIRED_COLUMNS].copy()
    body["material"] = body["材料分类"].astype(str).str.strip()
    body["gsm_label"] = body["规格克重"].astype(str).str.strip()
    if (body["material"] == "").any() or (body["gsm_label"] == "").any():
        raise PriceDatabaseError("袋身材料分类和规格克重不能为空。")

    gsm_text = body["gsm_label"].str.extract(r"(\d+(?:\.\d+)?)", expand=False)
    body["gsm"] = _numeric(gsm_text, "规格克重", BODY_SHEET)
    body["price_per_m2"] = _numeric(
        body["每平方米单价(元)"], "每平方米单价(元)", BODY_SHEET
    )
    duplicate_body = body.duplicated(["material", "gsm_label"], keep=False)
    if duplicate_body.any():
        keys = (
            body.loc[duplicate_body, ["material", "gsm_label"]]
            .drop_duplicates()
            .astype(str)
            .agg(" / ".join, axis=1)
            .tolist()
        )
        raise PriceDatabaseError(f"袋身材料查价键重复：{'; '.join(keys)}。")

    for material, rows in body.groupby("material"):
        ordered = rows.sort_values("gsm")
        prices = ordered["price_per_m2"].tolist()
        labels = ordered["gsm_label"].tolist()
        for index in range(1, len(prices)):
            if prices[index] < prices[index - 1]:
                warnings.append(
                    f"价格异常提醒：{material} {labels[index]} 的单价低于前一克重。"
                )

    body = body[
        ["material", "gsm_label", "gsm", "price_per_m2"]
    ].reset_index(drop=True)

    webbing_raw = _clean_columns(frames[WEBBING_SHEET])
    _require_columns(webbing_raw, WEBBING_REQUIRED_COLUMNS, WEBBING_SHEET)
    if "材料" in webbing_raw.columns:
        material_names = webbing_raw["材料"].astype(str).str.strip()
        color_rows = material_names.eq("PP织带 颜色")
        if color_rows.any():
            webbing_raw = webbing_raw.loc[color_rows].copy()
        else:
            warnings.append(
                "织带表未找到“PP织带 颜色”，系统按样式和宽度选取最高单价。"
            )

    webbing = webbing_raw.loc[:, WEBBING_REQUIRED_COLUMNS].copy()
    webbing["style"] = webbing["样式"].astype(str).str.strip()
    if (webbing["style"] == "").any():
        raise PriceDatabaseError("织带样式不能为空。")
    webbing["width_cm"] = _numeric(
        webbing["宽度（公分）"], "宽度（公分）", WEBBING_SHEET
    )
    webbing["grams_per_m"] = _numeric(
        webbing["每米克重"], "每米克重", WEBBING_SHEET
    )
    webbing["price_per_m"] = _numeric(
        webbing["每米单价（元）"], "每米单价（元）", WEBBING_SHEET
    )

    if "材料" in frames[WEBBING_SHEET].columns and not (
        frames[WEBBING_SHEET]["材料"].astype(str).str.strip() == "PP织带 颜色"
    ).any():
        webbing = (
            webbing.sort_values("price_per_m")
            .groupby(["style", "width_cm"], as_index=False)
            .tail(1)
        )

    duplicate_webbing = webbing.duplicated(["style", "width_cm"], keep=False)
    if duplicate_webbing.any():
        keys = (
            webbing.loc[duplicate_webbing, ["style", "width_cm"]]
            .drop_duplicates()
            .astype(str)
            .agg(" / ".join, axis=1)
            .tolist()
        )
        raise PriceDatabaseError(f"织带查价键重复：{'; '.join(keys)}。")

    webbing = webbing[
        ["style", "width_cm", "grams_per_m", "price_per_m"]
    ].sort_values(["style", "width_cm"]).reset_index(drop=True)
    if body.empty or webbing.empty:
        raise PriceDatabaseError("价格库不能是空表。")

    return PriceData(
        body=body,
        webbing=webbing,
        warnings=tuple(dict.fromkeys(warnings)),
        modified_at=modified_at,
        fingerprint=fingerprint,
    )


def read_price_database_bytes(
    content: bytes, *, modified_at: datetime | None = None
) -> PriceData:
    if not content:
        raise PriceDatabaseError("上传的Excel文件为空。")
    fingerprint = sha256(content).hexdigest()
    try:
        frames = pd.read_excel(BytesIO(content), sheet_name=None, engine="openpyxl")
    except Exception as exc:
        raise PriceDatabaseError(f"无法读取Excel：{exc}") from exc
    return validate_frames(
        frames,
        modified_at=modified_at or datetime.now(timezone.utc),
        fingerprint=fingerprint,
    )


def load_price_database(path: Path) -> PriceData:
    try:
        content = path.read_bytes()
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError as exc:
        raise PriceDatabaseError(f"无法读取价格库“{path}”：{exc}") from exc
    return read_price_database_bytes(content, modified_at=modified_at)


def ensure_runtime_database(seed_path: Path, target_path: Path) -> PriceData:
    if target_path.exists():
        return load_price_database(target_path)
    seed_data = load_price_database(seed_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(seed_path.read_bytes())
    os.replace(temporary, target_path)
    return seed_data


def install_price_database(
    content: bytes,
    *,
    target_path: Path,
    backup_dir: Path,
) -> PriceData:
    validated = read_price_database_bytes(content)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    with _INSTALL_LOCK:
        if target_path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_name = (
                f"price_database_{stamp}_{validated.fingerprint[:8]}.xlsx"
            )
            shutil.copy2(target_path, backup_dir / backup_name)

        temporary = target_path.with_name(
            f".{target_path.name}.{uuid.uuid4().hex}.uploading"
        )
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target_path)
        finally:
            temporary.unlink(missing_ok=True)

        backups = sorted(
            backup_dir.glob("price_database_*.xlsx"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[MAX_BACKUPS:]:
            stale.unlink(missing_ok=True)

    return load_price_database(target_path)
