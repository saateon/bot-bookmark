# -*- coding: utf-8 -*-
"""
ماژول اصلی — ربات تلگرام و هماهنگی جزیره‌ها.

جریان یک لینک:
    پیام تلگرام → استخراج URL → reader.fetch → ai.generate_title
    → store.add_link → پاسخ به کاربر

این فایل هیچ منطق دامنه‌ای ندارد (نه صفحه می‌خواند، نه عنوان می‌سازد،
نه JSON می‌نویسد) — فقط ماژول‌های همسایه را به ترتیب صدا می‌زند و
خطاها را به پیام‌های فارسی خوانا تبدیل می‌کند.

اجرا:
    python bot.py            (نیاز به .env دارد — نمونه: .env.example)
"""
from __future__ import annotations

import logging
import re
import sys
import time

import httpx

import ai
import config
import reader
import store
from ai import TitleResult

log = logging.getLogger("bot")

# ------------------------------------------------------------------ تلگرام

TG_API = "https://api.telegram.org/bot" + config.BOT_TOKEN

HELP_TEXT = (
    "🤖 ربات لینک — دستیارِ «مدیر لینک»\n\n"
    "هر لینکی بفرست؛ صفحه‌اش خوانده می‌شود، یک عنوانِ خلاصهٔ فارسی برایش "
    "ساخته می‌شود و در دستهٔ bot ذخیره می‌شود.\n\n"
    "فرمان‌ها:\n"
    "/id — آیدی عددی همین چت (برای ALLOWED_CHATS)\n"
    "/ping — وضعیت اتصال به داده\n"
    "/help — همین راهنما"
)


def tg_call(client: httpx.Client, method: str, params: dict) -> dict | None:
    r = client.post(f"{TG_API}/{method}", json=params, timeout=60)
    data = r.json()
    if not data.get("ok"):
        log.error("telegram %s failed: %s", method, data)
        return None
    return data.get("result")


def send(client: httpx.Client, chat_id: int, text: str) -> None:
    tg_call(client, "sendMessage", {"chat_id": chat_id, "text": text[:4000]})


# ------------------------------------------------------------- استخراج لینک

# لینک کامل، یا www.، یا دامنهٔ لخت با پسوندهای رایج (فارسی و خارجی)
_RE_URL = re.compile(
    r"""(?:
        https?://[^\s<>"'\[\]()]+
        | www\.[^\s<>"'\[\]()]+
        | (?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+
          (?:com|net|org|ir|io|dev|app|ai|me|co|info|xyz|shop|site|online|tech|store|pro|tv|news|blog|cloud)
          (?:/[^\s<>"'\[\]()]*)?
    )""",
    re.I | re.X,
)
_TRAIL = ".,;:!?،؛…)»\"'"


def extract_urls(text: str) -> list[str]:
    out = []
    for m in _RE_URL.findall(text) or []:
        u = m.strip().rstrip(_TRAIL)
        if not u:
            continue
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        if u not in out:
            out.append(u)
    return out


# ------------------------------------------------------------- پردازش لینک

def process_link(client: httpx.Client, chat_id: int, raw_url: str) -> None:
    """یک لینک را از خواندن تا ذخیره پیش می‌برد و نتیجه را می‌فرستد."""
    try:
        page = reader.fetch(raw_url)
    except reader.ReaderError as e:
        log.warning("reader failed for %s: %s", raw_url, e)
        # صفحه باز نشد ولی شاید آدرس درست باشد — بدون عنوان ذخیره می‌کنیم
        result: TitleResult = TitleResult(title=store.domain_of(raw_url) or raw_url, source="domain")
    else:
        result = ai.generate_title(page)

    try:
        status, item = store.add_link(raw_url, result.title, note="")
    except store.StoreError as e:
        send(client, chat_id, f"❌ ذخیره نشد: {e}")
        return

    if status == "duplicate":
        send(client, chat_id, f"♻️ از قبل بود: {item.get('title') or item.get('url')}")
        return

    source_fa = {"ai": "هوش مصنوعی", "meta": "توضیح صفحه", "page": "عنوان صفحه", "domain": "دامنه"}[result.source]
    send(client, chat_id, f"✅ ذخیره شد [{source_fa}]:\n{result.title}\n{item['url']}")
    log.info("stored %s via %s", item["id"], result.source)


# ------------------------------------------------------------- پیام‌رسانی

def handle_message(client: httpx.Client, msg: dict) -> None:
    chat_id = msg["chat"]["id"]

    if chat_id not in config.ALLOWED_CHATS:
        log.warning("ignored message from unauthorized chat %s", chat_id)
        return  # بی‌پاسخ — بات شخصی است

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text:
        return

    if text.startswith("/"):
        handle_command(client, chat_id, text.split()[0].split("@")[0].lower())
        return

    urls = extract_urls(text)
    if not urls:
        send(client, chat_id, "لینکی در پیام پیدا نشد. فقط دامنه یا آدرس کامل بفرست.")
        return

    if len(urls) > 1:
        send(client, chat_id, f"📥 {len(urls)} لینک دریافت شد؛ یکی‌یکی پردازش می‌شوند…")

    for u in urls:
        process_link(client, chat_id, u)


def handle_command(client: httpx.Client, chat_id: int, cmd: str) -> None:
    if cmd in ("/start", "/help"):
        send(client, chat_id, HELP_TEXT)
    elif cmd == "/id":
        send(client, chat_id, f"آیدی این چت:\n{chat_id}\n\nاین عدد را در ALLOWED_CHATS فایل .env بگذارید.")
    elif cmd == "/ping":
        try:
            s = store.stats()
            send(client, chat_id,
                 f"🏓 داده در دسترس است.\nشاردها: {s['shards']} — کل آیتم‌ها: {s['items']} — دستهٔ {config.CATEGORY}: {s['bot_items']}")
        except Exception as e:  # noqa: BLE001
            send(client, chat_id, f"🏓 مشکل در دسترسی به داده: {e}")
    else:
        send(client, chat_id, "فرمان ناشناخته. /help را ببین.")


# ------------------------------------------------------------- حلقهٔ اصلی

def run() -> None:
    errors = config.validate()
    if errors:
        print("⛔ ربات بالا نیامد — مشکلات پیکربندی:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    log.info("bot starting — model=%s data=%s category=%s",
             config.AI_MODEL, config.DATA_DIR, config.CATEGORY)

    offset = 0
    backoff = 3
    with httpx.Client(timeout=httpx.Timeout(config.TG_POLL_TIMEOUT + 15, connect=15)) as client:
        me = tg_call(client, "getMe", {})
        if me:
            log.info("authorized as @%s", me.get("username"))

        while True:
            try:
                updates = tg_call(client, "getUpdates", {
                    "offset": offset,
                    "timeout": config.TG_POLL_TIMEOUT,
                    "allowed_updates": ["message"],
                }) or []
                backoff = 3
                for upd in updates:
                    offset = max(offset, upd["update_id"] + 1)
                    msg = upd.get("message")
                    if msg:
                        handle_message(client, msg)
            except KeyboardInterrupt:
                log.info("stopped by user")
                break
            except (httpx.HTTPError, Exception) as e:  # noqa: BLE001
                log.error("poll loop error: %s — retry in %ss", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    run()


if __name__ == "__main__":
    main()
