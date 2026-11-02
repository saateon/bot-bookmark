# -*- coding: utf-8 -*-
"""
ماژول ذخیره — پل میان ربات و دادهٔ برنامهٔ بوکمارک (PHP).

اصل طراحی: ربات «مهمانِ» برنامهٔ PHP است و هیچ فایل کد آن را تغییر
نمی‌دهد. فقط همان ساختار JSON ای را می‌نویسد که PHP می‌نویسد:

    shards/<slug>.json   منبع حقیقت آیتم‌ها (ما فقط shards/<CATEGORY>.json)
    categories.json      فهرست دسته‌ها
    .write.lock          قفل مشترک نوشتن — همان فایلی که PHP هم flock می‌کند
    index.json           دست نمی‌زنیم! PHP با اثر انگشت mtime+size خودش
                         متوجه تغییر می‌شود و ایندکس را بازمی‌سازد
                         (core/store.php تابع stamp) — برای همین لینک‌های
                         ربات بدون هیچ تغییری در کد PHP در برنامه دیده می‌شوند.

هم‌ارزی با PHP (آینه‌شدن منطق ۲۰-bookmarks.php):
    normalize_url  ≈  bm_normalize_url
    dupe_key       ≈  bm_dupe_key
    domain_of      ≈  bm_domain
    color_for      ≈  bm_color_for (پالت یکسان، crc32 یکسان)
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
import zlib
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import config

log = logging.getLogger("store")

# همان پالت PHP — دست نزنید تا رنگ دسته‌های ربات با بقیهٔ برنامه هماهنگ بماند.
_PALETTE = ["#3355A3", "#3385A3", "#33A38D", "#33A35C", "#4633A3", "#7A33A3", "#A36F33", "#A34233"]


class StoreError(Exception):
    """نوشتن در داده ممکن نشد."""


# --------------------------------------------------------------- آدرس‌ها

_RE_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.I)


def normalize_url(u: str) -> str:
    """آینهٔ bm_normalize_url: فقط http/https، میزبان الزامی، بدون fragment."""
    u = (u or "").strip()
    if not u:
        return ""
    if not _RE_SCHEME.match(u):
        u = "https://" + u

    try:
        p = urlsplit(u)
    except ValueError:
        return ""
    if not p.hostname:
        return ""

    scheme = (p.scheme or "https").lower()
    if scheme not in ("http", "https"):
        return ""  # javascript: و data: همین‌جا رد می‌شوند

    host = p.hostname.lower()
    try:
        port = p.port or 0
    except ValueError:
        return ""
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = 0

    path = p.path or "/"
    query = f"?{p.query}" if p.query else ""
    netloc = host if not port else f"{host}:{port}"
    return urlunsplit((scheme, netloc, path, query, ""))


def dupe_key(url: str) -> str:
    """آینهٔ bm_dupe_key: http/https و www و اسلش آخر یکسان حساب می‌شوند."""
    try:
        p = urlsplit(url)
    except ValueError:
        return (url or "").strip().lower()
    if not p.hostname:
        return (url or "").strip().lower()

    host = re.sub(r"^www\.", "", p.hostname.lower(), flags=re.I)
    path = (p.path or "").rstrip("/") or "/"
    query = ""
    if p.query:
        pairs = parse_qsl(p.query, keep_blank_values=True)
        pairs.sort(key=lambda kv: kv[0])  # ≈ ksort در PHP
        query = "?" + urlencode(pairs)
    return host + path + query


def domain_of(url: str) -> str:
    try:
        h = urlsplit(url).hostname or ""
    except ValueError:
        h = ""
    return re.sub(r"^www\.", "", h.lower(), flags=re.I)


def color_for(slug: str) -> str:
    # PHP: abs(crc32($slug)) % 8 — crc32 در پایتون هم unsigned 32 بیتی است.
    return _PALETTE[(zlib.crc32(slug.encode("utf-8")) & 0xFFFFFFFF) % len(_PALETTE)]


# --------------------------------------------------------------- قفل و IO

class DataLock:
    """
    قفل مشترک با PHP روی همان فایل .write.lock.
    روی لینوکس flock (سازگار با PHP)، روی ویندوز msvcrt، و اگر هیچ‌کدام
    نبود بی‌صدا ادامه می‌دهد (تست محلی).
    """

    def __init__(self, path: Path):
        self._path = path
        self._fh = None

    def __enter__(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "a+")
        try:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            try:
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                log.debug("advisory lock unavailable; continuing unlocked")
        except OSError as e:
            log.warning("flock failed: %s", e)
        return self

    def __exit__(self, *exc):
        try:
            try:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except ImportError:
                try:
                    import msvcrt

                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except (ImportError, OSError):
                    pass
        finally:
            self._fh.close()
            self._fh = None
        return False


def read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return default
        return json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        log.error("cannot read %s: %s — using default", path.name, e)
        return default


def write_json(path: Path, data) -> None:
    """نوشتن اتمیک، هم‌سبک PHP: فایل موقت، بعد replace. هرگز فایل نیمه‌نوشته نمی‌ماند."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    try:  # روی ویندوز اثری ندارد
        os.chmod(path, 0o660)
    except OSError:
        pass


# --------------------------------------------------------------- ساختار داده

def _shard_path(slug: str) -> Path:
    return config.DATA_DIR / "shards" / f"{slug}.json"


def ensure_tree() -> None:
    """زیرپوشه‌های لازم داده — آینهٔ ensureTree در paths.php (حداقلِ لازم)."""
    (config.DATA_DIR / "shards").mkdir(parents=True, exist_ok=True)
    guard = config.DATA_DIR / "index.html"
    if not guard.is_file():
        guard.write_text("", encoding="utf-8")


def categories() -> list[dict]:
    data = read_json(config.DATA_DIR / "categories.json", None)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
        return [{"slug": "bedoon-daste", "name": "بدون دسته", "color": "#79818F", "order": 999}]
    return data["items"]


def ensure_category(slug: str, display_name: str) -> None:
    """اگر دسته نیست، بساز — با رنگ پالت یکسان برنامه."""
    path = config.DATA_DIR / "categories.json"
    data = read_json(path, None)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        data = {"version": 2, "items": []}
    if any(c.get("slug") == slug for c in data["items"]):
        return
    data["items"].append({
        "slug": slug,
        "name": display_name,
        "color": color_for(slug),
        "order": len(data["items"]),
    })
    write_json(path, data)
    log.info("category created: %s", slug)


def _load_shard(slug: str) -> dict:
    data = read_json(_shard_path(slug), None)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        data = {"version": 2, "slug": slug, "items": []}
    return data


def _save_shard(slug: str, items: list[dict]) -> None:
    write_json(_shard_path(slug), {
        "version": 2,
        "slug": slug,
        "updated_at": int(time.time()),
        "items": list(items),
    })


def _all_shard_slugs() -> list[str]:
    d = config.DATA_DIR / "shards"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


# --------------------------------------------------------------- عملیات اصلی

def add_link(url: str, title: str, note: str = "") -> tuple[str, dict]:
    """
    افزودن یک لینک به دستهٔ config.CATEGORY.

    خروجی: ("added", item) یا ("duplicate", existing_item)
    index.json عمداً دست نمی‌خورد — PHP خودش آن را بازمی‌سازد.
    """
    url = normalize_url(url)
    if not url:
        raise StoreError("آدرس معتبر نیست — فقط http و https پذیرفته می‌شود.")

    key = dupe_key(url)
    slug = config.CATEGORY

    with DataLock(config.DATA_DIR / ".write.lock"):
        # تکراری؟ همان منطق PHP: کل همهٔ شاردها، فقط آیتم‌های حذف‌نشده
        for other in _all_shard_slugs():
            for it in _load_shard(other)["items"]:
                if it.get("deleted"):
                    continue
                if it.get("key", "") == key or it.get("url") == url:
                    log.info("duplicate: %s", url)
                    return "duplicate", it

        ensure_tree()
        ensure_category(slug, slug)

        now = int(time.time())
        item = {
            "id": "bm_" + secrets.token_hex(8),  # همان الگوی bm_ + ۱۶ نویسهٔ hex در PHP
            "url": url,
            "key": key,
            "title": title,
            "note": note,
            "domain": domain_of(url),
            "categories": [slug],
            "pinned": False,
            "archived": False,
            "deleted": False,
            "clicks": 0,
            "created_at": now,
            "updated_at": now,
            "shard": slug,  # PHP هم این فیلد را داخل آیتم ذخیره می‌کند (putItem)
        }

        shard = _load_shard(slug)
        shard["items"].append(item)
        _save_shard(slug, shard["items"])

    log.info("added %s → %s", item["id"], url)
    return "added", item


def stats() -> dict:
    """شمارش سریع برای /ping."""
    out = {"shards": 0, "items": 0, "bot_items": 0}
    for slug in _all_shard_slugs():
        out["shards"] += 1
        items = _load_shard(slug)["items"]
        out["items"] += len(items)
        if slug == config.CATEGORY:
            out["bot_items"] = len(items)
    return out
