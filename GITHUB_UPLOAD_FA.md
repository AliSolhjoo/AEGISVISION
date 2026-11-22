# راهنمای ارسال AEGISVISION به GitHub

این بسته برای آپلود سورس آماده شده است؛ فایل‌های دیتابیس، ویدئوها، فریم‌ها، کلیدها، `node_modules` و فایل‌های موقت در آن قرار ندارند.

## روش پیشنهادی: ارسال با Git

1. فایل ZIP را Extract کن.
2. در CMD یا PowerShell وارد پوشه اصلی استخراج‌شده شو؛ همان پوشه‌ای که `README.md` و `requirements.txt` در آن قرار دارند.
3. چون مخزن `AliSolhjoo/AEGISVISION` در زمان آماده‌سازی این بسته خالی بود، می‌توانی اولین commit را مستقیماً بسازی:

```bash
git init
git branch -M main
git remote add origin https://github.com/AliSolhjoo/AEGISVISION.git
git add .
git status --short
git diff --cached --stat
git commit -m "Initial commit: AEGISVISION 1.5.0"
git push -u origin main
```

اگر `git remote add origin` خطا داد که remote از قبل وجود دارد، ابتدا `git remote -v` را اجرا کن و remote درست را نگه دار؛ آن را دوباره اضافه نکن.

## اگر مخزن GitHub دیگر خالی نبود

در این حالت از پوشه استخراج‌شده مستقیماً push نکن. ابتدا مخزن را clone کن، سورس بسته را داخل پوشه clone‌شده کپی کن، سپس `git status` را بررسی و commit/push عادی انجام بده. از `--force` استفاده نکن مگر آگاهانه تصمیم گرفته باشی تاریخچه قبلی را جایگزین کنی.

## آپلود از طریق مرورگر GitHub

صفحه **Add file → Upload files** فایل ZIP را خودکار Extract نمی‌کند. ابتدا ZIP را روی کامپیوتر Extract کن و فایل‌ها و پوشه‌های داخل ریشه پروژه را بارگذاری کن. برای یک پروژه چندپوشه‌ای، روش Git معمولاً مطمئن‌تر و ساده‌تر است.

## بررسی امنیت قبل از Push

قبل از commit مطمئن شو این موارد را اضافه نکرده‌ای:

- فایل `.env` واقعی؛ فقط `.env.example` باید منتشر شود.
- `backend/db.sqlite3` یا هر دیتابیس شخصی.
- `backend/media/`، ویدئوها، فریم‌ها و تصاویر خصوصی.
- رمز دوربین، آدرس استریم حاوی نام‌کاربری/رمز، SMTP password یا API token.
- پوشه `frontend/node_modules/` یا فایل‌های cache و backup.

در پایان `git status --short` و `git diff --cached --stat` را بررسی کن و سپس commit/push بزن.
