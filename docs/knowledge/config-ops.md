# پیکربندی، اجرا، تست، استقرار

## config.py — تنها منبع حقیقت
همه از `.env` کنار کد (python-dotenv اختیاری؛ نبودش فقط یعنی .env خوانده نمی‌شود).
`validate()` پیش از اجرا بررسی می‌کند: BOT_TOKEN، ALLOWED_CHATS، AI_API_KEY، AI_MODEL، وجود و نوشتنی‌بودن DATA_DIR — ربات بدون این‌ها بالا نمی‌آید.

## متغیرهای .env (پیش‌فرض)
| متغیر | پیش‌فرض | نکته |
|---|---|---|
| BOT_TOKEN | — اجباری | از BotFather |
| ALLOWED_CHATS | — اجباری | آیدی عددی، جدا با کاما (فاصله و «،» فارسی هم پذیرفته)؛ با /id بگیر |
| AI_BASE_URL | https://router.vividplayer.net/v1 | سازگار OpenAI (۹router) |
| AI_API_KEY | — اجباری | همان ROUTER_API_KEY |
| AI_MODEL | — اجباری | نام مدل/کومبو از پنل ۹router |
| AI_MAX_TOKENS | 3000 | زیر ۳۰۰۰ نگذار (الزام ۹router) |
| AI_TEMPERATURE | 0.3 | پایین نگه دار |
| AI_TIMEOUT | 90 | مدل‌های reasoning کندند |
| DATA_DIR | /security_folder/data/bookmark | همان BM_DATA_DIR برنامهٔ PHP |
| CATEGORY | bot | دستهٔ مقصد لینک‌های ربات |
| TITLE_MAX_LEN | 80 | حداکثر طول عنوان |
| FETCH_TIMEOUT | 20 | ثانیه |
| LOG_LEVEL | info | debug/info/warning/error |

ثابت‌های داخل کد: `TG_POLL_TIMEOUT=50` (bot)، `USER_AGENT` (config)، `MAX_TEXT_CHARS=6000` (reader)، `_MAX_RETRIES=2` (ai)، `_PALETTE` (store).

## اجرا و تست
```bash
pip install -r requirements.txt   # فقط httpx + python-dotenv
cp .env.example .env              # مقادیر واقعی را بگذار
python bot.py
python selftest.py                # آفلاین: هم‌ارزی PHP، ساختار داده، تکراری + سطل زباله، پاک‌سازی HTML
python selftest.py --net          # + یک fetch واقعی از example.com
```
ترفند selftest: قبل از import کردن config، متغیر محیطی `DATA_DIR` را به پوشهٔ موقت می‌برد — ترتیب import مهم است.

## استقرار
- DATA_DIR باید همان پوشهٔ دادهٔ برنامهٔ PHP باشد؛ به همین جهت لینک‌های ربات بی‌هیچ تغییری در کد PHP در رابط آن دیده می‌شوند.
- اگر بات روی همان هاستِ AI و در شبکهٔ داکری ai-network باشد: `AI_BASE_URL=http://9router:20128/v1`
- توسعه روی ویندوز، اجرا روی لینوکس — کد هر دو را پوشش می‌دهد (قفل msvcrt/flock، chmod بی‌اثر در ویندوز).
