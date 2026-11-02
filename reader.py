# -*- coding: utf-8 -*-
"""
ماژول خواننده — لینک را باز می‌کند و عنوان + متن پاک صفحه را برمی‌دارد.

ورودی: یک رشتهٔ URL
خروجی: Page(url, title, text) — title برای حالت جایگزین (fallback)،
text برای فرستادن به هوش مصنوعی.

بی‌وابستگی عمدی: به جای کتابخانه‌های سنگین استخراج متن، از HTMLParsing
سبک با regex استفاده می‌کنیم تا روی هاست‌های کم‌امکانات هم نصب شود.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

import config

log = logging.getLogger("reader")

# حداکثر نویسه‌ای که از متن صفحه نگه می‌داریم — برای عنوان خلاصه کافی است.
MAX_TEXT_CHARS = 6000


class ReaderError(Exception):
    """صفحه باز نشد یا چیزی قابل خواندن نداشت."""


@dataclass
class Page:
    url: str
    title: str = ""
    text: str = ""
    meta_desc: str = ""
    http_status: int = 0
    content_type: str = ""
    tried_encodings: list[str] = field(default_factory=list)


# --- رمزگشایی -----------------------------------------------------------------

_FALLBACK_ENCODINGS = ["utf-8", "cp1256", "latin-1"]  # cp1256 برای سایت‌های فارسی قدیمی


def _decode(raw: bytes, content_type: str) -> tuple[str, list[str]]:
    """بایت‌ها را با متادیتای صفحه (و در نبودش، حدس) رمزگشایی می‌کند."""
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    chain: list[str] = []
    if m:
        chain.append(m.group(1).lower())
    chain += [e for e in _FALLBACK_ENCODINGS if e not in chain]

    for enc in chain:
        try:
            return raw.decode(enc), chain
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), chain


# --- استخراج ------------------------------------------------------------------

_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_RE_OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', re.I | re.S)
_RE_META_DESC = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.I | re.S)
_RE_STRIP = re.compile(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>", re.I | re.S)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_ENTITY = re.compile(r"&#(\d+);")


def _unescape(s: str) -> str:
    s = _RE_ENTITY.sub(lambda m: chr(int(m.group(1))), s)
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                    ("&#39;", "'"), ("&nbsp;", " "), ("&mdash;", "—"), ("&laquo;", "«"), ("&raquo;", "»")):
        s = s.replace(ent, ch)
    return s


def _clean(html: str) -> tuple[str, str, str]:
    """(عنوان، توضیح متا، متن پاک) را از HTML بیرون می‌کشد."""
    m = _RE_OG_TITLE.search(html) or _RE_TITLE.search(html)
    title = _RE_WS.sub(" ", _unescape(m.group(1))).strip() if m else ""

    m = _RE_META_DESC.search(html)
    meta = _RE_WS.sub(" ", _unescape(m.group(1))).strip() if m else ""

    body = _RE_STRIP.sub(" ", html)
    body = _RE_TAG.sub(" ", body)
    body = _unescape(body)
    body = _RE_WS.sub(" ", body).strip()

    return title[:200], meta[:300], body[:MAX_TEXT_CHARS]


# --- نقطهٔ ورود -----------------------------------------------------------------

def fetch(url: str) -> Page:
    """لینک را باز می‌کند. هر خرابی با ReaderError اعلام می‌شود."""
    headers = {"User-Agent": config.USER_AGENT, "Accept-Language": "fa,en;q=0.8"}
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=config.FETCH_TIMEOUT,
            headers=headers,
            verify=True,
        ) as c:
            r = c.get(url)
    except httpx.HTTPError as e:
        raise ReaderError(f"باز نشد: {type(e).__name__}") from e

    ctype = r.headers.get("content-type", "")
    if r.status_code >= 400:
        raise ReaderError(f"پاسخ سرور {r.status_code} بود")

    if "html" not in ctype and "xml" not in ctype and ctype != "":
        # PDF و مشابه: متن نداریم، فقط متادیتا
        page = Page(url=url, http_status=r.status_code, content_type=ctype)
        page.title = ""
        page.text = ""
        return page

    html, tried = _decode(r.content, ctype)
    title, meta, text = _clean(html)

    page = Page(
        url=str(r.url),
        title=title,
        text=text,
        meta_desc=meta,
        http_status=r.status_code,
        content_type=ctype,
        tried_encodings=tried,
    )
    log.debug("fetched %s title=%r text_len=%d", url, title[:50], len(text))
    return page
