from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import threading
import uuid


DEFAULT_EXCHANGE_RATE = 6.7
DEFAULT_COMPANY_NAME_EN = ""
DEFAULT_SUPPLIER_CONTACT_EN = """Luke Xiang | Executive Sales Manager
Wenzhou Lianhai Bag Co., Ltd.

Mobile: +86 173 9809 9207 | Email: lhk@lianhaibag.com
Website: www.wenzhoulianhaibag.com

Factory Address: No. 1299, Keji Road, BSN Industrial Complex,
Wenzhou, Zhejiang, China 325802"""
_SETTINGS_LOCK = threading.Lock()


@dataclass(frozen=True)
class AppSettings:
    exchange_rate: float
    company_name_en: str
    supplier_contact_en: str
    updated_at: str


@dataclass(frozen=True)
class SettingsLoadResult:
    settings: AppSettings
    warning: str | None = None


def _default_settings() -> AppSettings:
    return AppSettings(
        exchange_rate=DEFAULT_EXCHANGE_RATE,
        company_name_en=DEFAULT_COMPANY_NAME_EN,
        supplier_contact_en=DEFAULT_SUPPLIER_CONTACT_EN,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def load_settings(path: Path) -> SettingsLoadResult:
    if not path.exists():
        return SettingsLoadResult(_default_settings())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        exchange_rate = float(payload["exchange_rate"])
        if exchange_rate <= 0:
            raise ValueError("汇率必须大于0")
        company_name_en = str(payload.get("company_name_en") or "").strip()
        supplier_contact_en = str(
            payload.get("supplier_contact_en") or DEFAULT_SUPPLIER_CONTACT_EN
        ).strip()
        updated_at = str(payload.get("updated_at") or "")
        return SettingsLoadResult(
            AppSettings(exchange_rate, company_name_en, supplier_contact_en, updated_at)
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return SettingsLoadResult(
            _default_settings(),
            f"设置文件读取失败，暂时使用默认汇率{DEFAULT_EXCHANGE_RATE:g}：{exc}",
        )


def _save_settings(
    path: Path,
    *,
    exchange_rate: float,
    company_name_en: str,
    supplier_contact_en: str,
) -> AppSettings:
    if exchange_rate <= 0:
        raise ValueError("汇率必须大于0。")
    settings = AppSettings(
        exchange_rate=float(exchange_rate),
        company_name_en=company_name_en.strip(),
        supplier_contact_en=supplier_contact_en.strip(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    payload = {
        "exchange_rate": settings.exchange_rate,
        "company_name_en": settings.company_name_en,
        "supplier_contact_en": settings.supplier_contact_en,
        "updated_at": settings.updated_at,
    }
    path.parent.mkdir(parents=True, exist_ok=True)

    with _SETTINGS_LOCK:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return settings


def save_exchange_rate(path: Path, exchange_rate: float) -> AppSettings:
    current = load_settings(path).settings
    return _save_settings(
        path,
        exchange_rate=exchange_rate,
        company_name_en=current.company_name_en,
        supplier_contact_en=current.supplier_contact_en,
    )


def save_company_name(path: Path, company_name_en: str) -> AppSettings:
    current = load_settings(path).settings
    return _save_settings(
        path,
        exchange_rate=current.exchange_rate,
        company_name_en=company_name_en,
        supplier_contact_en=current.supplier_contact_en,
    )


def save_supplier_contact(path: Path, supplier_contact_en: str) -> AppSettings:
    current = load_settings(path).settings
    return _save_settings(
        path,
        exchange_rate=current.exchange_rate,
        company_name_en=current.company_name_en,
        supplier_contact_en=supplier_contact_en,
    )
