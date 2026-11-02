# -*- coding: utf-8 -*-
"""
ماژول هوش مصنوعی — تنها جایی که با ۹router حرف می‌زند.

نقش: دریافت متن صفحه، برگرداندن یک عنوان فارسیِ خلاصه.

قرارداد ماژول:
    generate_title(page) -> TitleResult(title, source)

source یکی از: ai | meta | page | domain
یعنی اگر هوش مصنوعی جواب نداد، زنجیرهٔ جایگزین خودکار فعال می‌شود و
ربات هرگز به‌خاطر خرابی AI از کار نمی‌افتد.

هیچ چت و حافظه‌ای وجود ندارد: هر فراخوانی یک درخواست مستقل با
پرامپت سیستمی ثابت است (prompts.py) — مدل هیچ اختیاری جز نوشتن
عنوان ندارد و خروجی‌اش سمت پایتون اعتبارسنجی می‌شود.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

import config
import store
from prompts import UNKNOWN_MARK, build_system_prompt

log = logging.getLogger("ai")

_MAX_RETRIES = 2  # یک تلاش اصلی + یک تلاش با پیام تذکر


@dataclass
class TitleResult:
    title: str
    source: str  # ai | meta | page | domain


class AIError(Exception):
    pass


def _chat(text: str) -> str:
    """یک فراخوانی خام به /chat/completions. متن پاسخ مدل را برمی‌گرداند."""
    payload = {
        "model": config.AI_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(config.TITLE_MAX_LEN)},
            {"role": "user", "content": text or "(متن خالی)"},
        ],
        "temperature": config.AI_TEMPERATURE,
        "max_tokens": config.AI_MAX_TOKENS,  # مستندات ۹router: ≥ ۳۰۰۰
    }
    headers = {"Authorization": f"Bearer {config.AI_API_KEY}"}
    url = f"{config.AI_BASE_URL}/chat/completions"

    try:
        with httpx.Client(timeout=config.AI_TIMEOUT) as c:
            r = c.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise AIError(f"ارتباط با {config.AI_BASE_URL} برقرار نشد: {type(e).__name__}") from e

    if r.status_code == 401:
        raise AIError("کلید API رد شد (401) — AI_API_KEY را بررسی کنید.")
    if r.status_code == 404:
        raise AIError("مدل پیدا نشد (404) — AI_MODEL را با پنل ۹router چک کنید.")
    if r.status_code != 200:
        raise AIError(f"پاسخ سرور هوش مصنوعی: {r.status_code}")

    try:
        data = r.json()
        return data["choices"][0]["message"]["content"] or ""
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise AIError("پاسخ مدل ساختار مورد انتظار را نداشت.") from e


def _sanitize(raw: str) -> str:
    """خروجی مدل را به یک خطِ تمیز تبدیل می‌کند."""
    line = (raw or "").strip().splitlines()
    line = line[0].strip() if line else ""
    line = line.strip("`\"'«»[] ").strip()
    line = line.rstrip(".")

    # اگر مدل وسط کار حرف زد و از قالب خارج شد، فقط بخش اول می‌ماند.
    return line


def generate_title(page) -> TitleResult:
    """
    از متنِ Page یک عنوان می‌سازد.

    زنجیرهٔ جایگزین:
      ai → meta (توضیح متای صفحه) → page (تگ title) → domain
    """
    hint = " ".join(x for x in (page.meta_desc, page.text) if x).strip()

    if hint:
        last_err: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                raw = _chat(hint)
            except AIError as e:
                last_err = e
                log.warning("ai attempt %d failed: %s", attempt, e)
                continue

            title = _sanitize(raw)
            if title == UNKNOWN_MARK or not title:
                log.info("model said unknown (attempt %d)", attempt)
                last_err = AIError("مدل نتوانست عنوان بسازد.")
                continue

            if len(title) > config.TITLE_MAX_LEN:
                title = title[: config.TITLE_MAX_LEN].rstrip()
            log.info("title from ai: %r", title)
            return TitleResult(title=title, source="ai")
        if last_err:
            log.warning("falling back after ai failure: %s", last_err)
    else:
        log.info("page had no readable text; skipping ai call")

    # --- جایگزین‌ها ---------------------------------------------------------
    if page.meta_desc:
        t = page.meta_desc[: config.TITLE_MAX_LEN].rstrip()
        return TitleResult(title=t, source="meta")
    if page.title:
        t = page.title[: config.TITLE_MAX_LEN].rstrip()
        return TitleResult(title=t, source="page")

    # آخرین چاره: از خود دامنه — همان منطق PHP برای عنوان پیش‌فرض
    d = store.domain_of(page.url) or page.url
    return TitleResult(title=d[: config.TITLE_MAX_LEN], source="domain")
