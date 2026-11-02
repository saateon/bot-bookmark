# reader.py — خواندن و پاک‌سازی صفحهٔ وب

## قرارداد
`fetch(url) → Page(url, title, text, meta_desc, http_status, content_type, tried_encodings)`
هر خرابی → `ReaderError` با پیام فارسی.

## رفتار fetch
- httpx با `follow_redirects=True`، timeout=`FETCH_TIMEOUT` (پیش‌فرض ۲۰ ثانیه)، UA از `config.USER_AGENT`، Accept-Language: fa,en
- status ≥ 400 → ReaderError
- content-type بدون html/xml (مثل PDF) → Page با title/text خالی — فقط متادیتا برمی‌گردد
- رمزگشایی به‌ترتیب: charset از هدر → utf-8 → cp1256 (سایت‌های فارسی قدیمی) → latin-1 → در شکستِ همه، utf-8 با replace

## استخراج — همه با regex
عمداً بدون BeautifulSoup و مشابه، برای نصب‌پذیری روی هاست‌های کم‌امکانات:
- title: `og:title` یا `<title>` — تا ۲۰۰ نویسه
- meta_desc: `meta[name=description]` — تا ۳۰۰ نویسه
- text: حذف `script/style/noscript/svg/head` → حذف همهٔ تگ‌ها → تبدیل entityهای HTML → فشرده‌سازی فاصله‌ها → برش به `MAX_TEXT_CHARS=6000`
- `_clean(html)` مستقیم قابل تست است (selftest همین تابع را می‌سنجد)

## نکتهٔ ادغام
bot.py خرابی reader را می‌پذیرد: ذخیره با عنوانِ دامنه ادامه می‌یابد (source=domain).
