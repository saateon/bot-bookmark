# -*- coding: utf-8 -*-
"""
ماژول پیکربندی — تنها منبع حقیقت تنظیمات ربات.

مقادیر از فایل `.env` کنار همین فایل خوانده می‌شوند (نمونه: `.env.example`).
هیچ مقدار حساسی (توکن، کلید) در کد نوشته نمی‌شود و کد بدون .env بالا نمی‌آید.

متغیرها:
    BOT_TOKEN        توکن ربات تلگرام از BotFather
    ALLOWED_CHATS    آیدی عددی چت‌های مجاز، جدا با کاما (با /id بگیرید)
    AI_BASE_URL      پایهٔ API سازگار با OpenAI — پیش‌فرض ۹router شما
    AI_API_KEY       کلید ROUTER_API_KEY
    AI_MODEL         نام مدل/کومبو در ۹router
    AI_MAX_TOKENS    سقف توکن پاسخ (مستندات ۹router: حداقل ۳۰۰۰)
    AI_TEMPERATURE   خلاقیت مدل — پایین نگه دارید
    DATA_DIR         مسیر پوشهٔ دادهٔ برنامهٔ بوکمارک (همان BM_DATA_DIR در PHP)
    CATEGORY         اسلاگ دستهٔ مقصد — پیش‌فرض bot
    TITLE_MAX_LEN    حداکثر طول عنوان تولیدی هوش مصنوعی
    FETCH_TIMEOUT    مهلت باز کردن لینک‌ها (ثانیه)
    LOG_LEVEL        debug | info | warning | error
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # بدون python-dotenv هم کار می‌کند، فقط .env خوانده نمی‌شود
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")


def _chat_ids(raw: str) -> list[int]:
    out = []
    for part in raw.replace("،", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


# --- تلگرام ---------------------------------------------------------------
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_CHATS: list[int] = _chat_ids(os.getenv("ALLOWED_CHATS", ""))
TG_POLL_TIMEOUT: int = 50  # طول long-poll تلگرام (ثانیه)

# --- هوش مصنوعی (۹router) ---------------------------------------------------
AI_BASE_URL: str = os.getenv("AI_BASE_URL", "https://router.vividplayer.net/v1").rstrip("/")
AI_API_KEY: str = os.getenv("AI_API_KEY", "").strip()
AI_MODEL: str = os.getenv("AI_MODEL", "").strip()
AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "3000") or 3000)
AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", "0.3") or 0.3)
AI_TIMEOUT: int = int(os.getenv("AI_TIMEOUT", "90") or 90)  # مدل‌های reasoning کندند

# --- دادهٔ بوکمارک -----------------------------------------------------------
DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/security_folder/data/bookmark"))
CATEGORY: str = os.getenv("CATEGORY", "bot").strip() or "bot"
TITLE_MAX_LEN: int = int(os.getenv("TITLE_MAX_LEN", "80") or 80)

# --- عمومی -------------------------------------------------------------------
FETCH_TIMEOUT: int = int(os.getenv("FETCH_TIMEOUT", "20") or 20)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").lower()
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
    "LinkBot/1.0"
)


def validate() -> list[str]:
    """فهرست خطاهای آماده‌شدن. خالی یعنی همه‌چیز مرتب است."""
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN تنظیم نشده. از BotFather بگیرید و در .env بگذارید.")
    if not ALLOWED_CHATS:
        errors.append("ALLOWED_CHATS خالی است. در تلگرام به بات /id بفرستید تا آیدی‌تان بیاید.")
    if not AI_API_KEY:
        errors.append("AI_API_KEY تنظیم نشده (همان ROUTER_API_KEY در ۹router).")
    if not AI_MODEL:
        errors.append("AI_MODEL تنظیم نشده. نام کومبو/مدل را از پنل ۹router کپی کنید.")
    if not DATA_DIR.exists():
        errors.append(f"DATA_DIR وجود ندارد: {DATA_DIR}")
    elif not os.access(DATA_DIR, os.W_OK):
        errors.append(f"DATA_DIR نوشتنی نیست: {DATA_DIR}")
    return errors
