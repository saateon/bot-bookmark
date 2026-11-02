# store.py — پل داده به برنامهٔ بوکمارک PHP

## اصل طراحی
ربات «مهمان» برنامهٔ PHP است: فقط همان فایل‌های داده‌ای را می‌نویسد که PHP می‌نویسد. هیچ فایل کد PHP تغییر نمی‌کند.

## فایل‌های داده (زیر `config.DATA_DIR`)
| فایل | نقش | سیاست ربات |
|---|---|---|
| `shards/<slug>.json` | منبع حقیقت آیتم‌ها | فقط شاردِ `CATEGORY` را می‌نویسد؛ برای تشخیص تکراری همهٔ شاردها را می‌خواند |
| `categories.json` | دسته‌ها: `{version:2, items:[{slug,name,color,order}]}` | اگر دسته نبود، می‌افزاید (رنگ از `color_for`) |
| `.write.lock` | قفل مشترک نوشتن با PHP | flock (لینوکس) / msvcrt (ویندوز)؛ نبود هر دو = ادامهٔ بی‌قفل (حالت تست) |
| `index.json` | ایندکس PHP | **هرگز دست نمی‌زنیم** — PHP با اثر انگشت mtime+size (تابع stamp در core/store.php) تغییر را می‌فهمد و بازش می‌سازد؛ به همین دلیل لینک‌های ربات بی‌هیچ تغییری در PHP دیده می‌شوند |
| `index.html` | گارد جلوگیری از directory-listing | اگر نبود، خالی ساخته می‌شود (`ensure_tree`) |

دستهٔ جایگزین وقتی categories.json غایب/خراب باشد: `bedoon-daste` (بدون دسته).

## هم‌ارزی با PHP (فایل `۲۰-bookmarks.php`) — این توابع را تغییر نده
| پایتون | PHP | قاعدهٔ مشترک |
|---|---|---|
| `normalize_url` | `bm_normalize_url` | فقط http/https (javascript: و data: رد)، میزبان الزامی، fragment حذف، پورت پیش‌فرض 80/443 حذف، www می‌ماند |
| `dupe_key` | `bm_dupe_key` | scheme + www + اسلشِ آخر بی‌اثر؛ پارامترهای query مرتب‌شده (ksort) |
| `domain_of` | `bm_domain` | hostname کوچک‌شده، بدون www |
| `color_for` | `bm_color_for` | `_PALETTE[(zlib.crc32(slug) & 0xFFFFFFFF) % 8]` — پالت ۸ رنگی ثابت، هماهنگ با PHP |

## شِما
شارد:
```json
{"version": 2, "slug": "<slug>", "updated_at": <epoch>, "items": [...]}
```
آیتم — دقیقاً همین ۱۴ فیلد، همان PHP؛ فیلد اضافه نکن:
```json
{"id": "bm_<16hex>", "url": "<نرمال‌شده>", "key": "<dupe_key>", "title": "", "note": "",
 "domain": "", "categories": ["bot"], "pinned": false, "archived": false,
 "deleted": false, "clicks": 0, "created_at": 0, "updated_at": 0, "shard": "bot"}
```

## عملیات
`add_link(url, title, note="") → ("added" | "duplicate", item)`
- زیر قفل: همهٔ شاردها برای `key` یا `url` یکسان جستجو می‌شوند؛ آیتم‌های `deleted=true` رد می‌شوند (سطل زباله مانع افزودن مجدد نیست) → تکراری
- در غیر این صورت: `ensure_tree` → `ensure_category` → append → ذخیره

`stats() → {shards, items, bot_items}` — برای دستور `/ping`.

## نوشتن همیشه اتمیک
`json.dumps(ensure_ascii=False, indent=2)` → فایل موقت با پسوند pid → `os.replace` → chmod 0660 (در ویندوز بی‌اثر). فایل نیمه‌نوشته هرگز باقی نمی‌ماند.
