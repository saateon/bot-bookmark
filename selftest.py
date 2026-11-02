# -*- coding: utf-8 -*-
"""
تست خودکار آفلاین — بدون تلگرام، بدون هوش مصنوعی، بدون اینترنت.

چه چیزی تست می‌شود:
    ۱. هم‌ارزی منطق آدرس‌ها با PHP (normalize_url / dupe_key)
    ۲. نوشتن صحیح در ساختار دادهٔ برنامه (ساختار شارد، دسته، آیتم)
    ۳. تشخیص تکراری
    ۴. پاک‌سازی HTML در reader

اجرا:
    python selftest.py           → تست‌های آفلاین
    python selftest.py --net     → + یک تست واقعی خواندن صفحه (نیاز اینترنت)

اگر همه سبز بود، ربات روی همین منطق روی سرور کار خواهد کرد.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# دادهٔ تست را قبل از خواندن config به پوشهٔ موقت می‌بریم
_TMP = tempfile.mkdtemp(prefix="bm-bot-selftest-")
os.environ["DATA_DIR"] = _TMP

import config  # noqa: E402
import reader  # noqa: E402
import store  # noqa: E402
from prompts import build_system_prompt  # noqa: E402

_PASS = 0
_FAIL = 0


def check(name: str, got, want) -> None:
    global _PASS, _FAIL
    if got == want:
        _PASS += 1
        print(f"  ✅ {name}")
    else:
        _FAIL += 1
        print(f"  ❌ {name}\n      got:  {got!r}\n      want: {want!r}")


def test_urls() -> None:
    print("\n[۱] هم‌ارزی آدرس‌ها با PHP (bm_normalize_url / bm_dupe_key)")

    check("بدون اسکیم → https اضافه شود",
          store.normalize_url("example.com"), "https://example.com/")

    check("میزبان کوچک و پورت پیش‌فرض حذف",
          store.normalize_url("http://Example.COM:80/a"), "http://example.com/a")

    check("fragment حذف شود، www در آدرس بماند (مثل PHP)",
          store.normalize_url("https://www.Site.com/x/#section"),
          "https://www.site.com/x")

    check("javascript: رد شود", store.normalize_url("javascript:alert(1)"), "")
    check("ftp: رد شود", store.normalize_url("ftp://files.x.com/f"), "")
    check("بدون میزبان رد شود", store.normalize_url("https://"), "")

    check("http/www/اسلش آخر همه یک کلید",
          store.dupe_key("http://a.com/x"),
          store.dupe_key("https://WWW.a.com/x/"))

    check("ترتیب پارامترها در کلید بی‌اثر باشد",
          store.dupe_key("https://a.com/p?b=2&a=1"),
          store.dupe_key("https://a.com/p?a=1&b=2"))

    check("دامنه بدون www", store.domain_of("https://WWW.Shop.Ir/a?b=1"), "shop.ir")


def test_store() -> None:
    print("\n[۲] ساختار داده — سازگاری با PHP")

    status, item = store.add_link("Example.com/Tools/Page", "جعبه‌ابزار آنلاین")
    check("اولین افزودن", status, "added")
    check("آیتم id با الگوی PHP", bool(__import__("re").match(r"^bm_[0-9a-f]{16}$", item["id"])), True)
    check("دستهٔ آیتم", item["categories"], [config.CATEGORY])
    check("دامنهٔ آیتم", item["domain"], "example.com")

    shard_path = config.DATA_DIR / "shards" / f"{config.CATEGORY}.json"
    check("فایل شارد ساخته شد", shard_path.is_file(), True)

    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    check("ساختار شارد (version/slug/items)",
          (shard.get("version"), shard.get("slug"), isinstance(shard.get("items"), list)),
          (2, config.CATEGORY, True))

    php_fields = {"id", "url", "key", "title", "note", "domain", "categories",
                  "pinned", "archived", "deleted", "clicks", "created_at",
                  "updated_at", "shard"}
    check("فیلدهای آیتم دقیقاً مثل PHP", set(shard["items"][0].keys()) >= php_fields, True)

    cats = json.loads((config.DATA_DIR / "categories.json").read_text(encoding="utf-8"))
    slugs = [c["slug"] for c in cats["items"]]
    check("دستهٔ bot در categories.json ثبت شد", config.CATEGORY in slugs, True)
    bot_cat = next(c for c in cats["items"] if c["slug"] == config.CATEGORY)
    check("دسته رنگ پالت دارد", bool(__import__("re").match(r"^#[0-9a-fA-F]{6}$", bot_cat["color"])), True)

    print("\n[۳] تشخیص تکراری")
    status2, item2 = store.add_link("https://example.com/Tools/Page", "دوباره")
    check("همان لینک با ظاهر دیگر", status2, "duplicate")

    status3, _ = store.add_link("https://other.site/x", "لینک دیگر")
    check("لینک متفاوت اضافه می‌شود", status3, "added")

    # شبیه‌سازی سطل زباله: آیتم حذف‌شده نباید مانع افزودن مجدد شود (مثل PHP)
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    shard["items"][0]["deleted"] = True
    shard_path.write_text(json.dumps(shard, ensure_ascii=False, indent=2), encoding="utf-8")
    status4, _ = store.add_link("http://www.example.com/tools/page/", "بازگشت از سطل")
    check("آیتم حذف‌شده (سطل زباله) مانع افزودن نیست", status4, "added")

    s = store.stats()
    check("آمار", (s["shards"] >= 1, s["bot_items"] == 2), (True, True))


def test_reader() -> None:
    print("\n[۴] پاک‌سازی HTML در reader")
    html = """
    <html><head><title>  آموزش    پایتون  </title>
    <script>evil()</script><style>.x{}</style></head>
    <body><h1>درس اول</h1><p>متنی دربارهٔ پایتون است.</p></body></html>
    """
    title, meta, text = reader._clean(html)
    check("عنوان استخراج و فاصله‌ها جمع شد", title, "آموزش پایتون")
    check("اسکریپت حذف شد", "evil" in text, False)
    check("متن بدنه آمد", "درس اول" in text and "پایتون" in text, True)

    check("پرامپت سیستمی طول مجاز را می‌گیرد",
          str(config.TITLE_MAX_LEN) in build_system_prompt(config.TITLE_MAX_LEN), True)


def test_reader_net() -> None:
    print("\n[۵] خواندن یک صفحهٔ واقعی (اینترنت)")
    try:
        p = reader.fetch("https://example.com")
        check("صفحه باز شد", p.http_status, 200)
        check("عنوان آمد", "Example" in p.title, True)
        check("متن خوانده شد", len(p.text) > 0, True)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ تست شبکه رد شد: {e}")


def main() -> None:
    print(f"پوشهٔ دادهٔ تست: {_TMP}")
    test_urls()
    test_store()
    test_reader()
    if "--net" in sys.argv:
        test_reader_net()

    print(f"\n{'='*50}\nنتیجه: {_PASS} پاس، {_FAIL} خطا")
    if _FAIL:
        sys.exit(1)
    print("همه چیز سبز است ✅")


if __name__ == "__main__":
    main()
