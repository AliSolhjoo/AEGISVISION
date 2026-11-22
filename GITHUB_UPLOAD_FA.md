# راهنمای نگهداری و ارسال AEGISVISION به GitHub

مخزن رسمی پروژه:
https://github.com/AliSolhjoo/AEGISVISION

## ارسال تغییرات از نسخه محلی موجود

اگر قبلاً مخزن را روی سیستم Clone کرده‌ای و Remote آن به مخزن بالا متصل است، از ریشه پروژه اجرا کن:

```powershell
git status
git remote -v
git pull --rebase origin main
git add .
git status
git diff --cached --stat
git commit -m "Describe your change"
git push origin main
```

اگر `git status` اعلام کرد working tree clean است، تغییری برای Commit وجود ندارد. اگر هنگام Pull تعارض ایجاد شد، ابتدا آن را حل کن و سپس ادامه بده. از `git push --force` برای رفع خطاهای معمول Push استفاده نکن.

## راه‌اندازی روی یک رایانه جدید

```powershell
git clone https://github.com/AliSolhjoo/AEGISVISION.git
cd AEGISVISION
```

سپس تغییراتت را اعمال و با دستورات بخش قبل Commit و Push کن.

## اگر سورس را از ZIP دریافت کرده‌ای

ZIP را Extract کن. برای به‌روزرسانی مخزن موجود، ابتدا آن را Clone کن و فایل‌های سورس استخراج‌شده را داخل پوشه Cloneشده کپی کن؛ فایل‌ها را روی پوشه `.git` کپی یا جایگزین نکن. سپس `git status` را بررسی و تغییرات را Commit و Push کن.

## آپلود از طریق مرورگر GitHub

صفحه **Add file → Upload files** فایل ZIP را خودکار Extract نمی‌کند. ابتدا ZIP را Extract کن و فایل‌ها و پوشه‌های داخل ریشه پروژه را بارگذاری کن. برای پروژه چندپوشه‌ای، Git روش مطمئن‌تری است.

## بررسی امنیت قبل از Commit

قبل از اجرای `git add .` مطمئن شو موارد زیر منتشر نمی‌شوند:

- فایل `.env` واقعی؛ فقط فایل‌های نمونه مانند `.env.example` مجازند.
- دیتابیس محلی مانند `backend/db.sqlite3`.
- `backend/media/`، ویدئوها، فریم‌ها و تصاویر خصوصی.
- رمز دوربین، URL استریم حاوی اطلاعات ورود، SMTP password یا API token.
- `frontend/node_modules/`، cache، log و فایل‌های پشتیبان.
- وزن‌های مدل یا فایل‌های حجیم که مجوز انتشار آن‌ها را نداری.

در پایان خروجی `git status --short` و `git diff --cached --stat` را بازبینی کن. هرگز برای حل مشکل Push بدون بررسی از `--force` استفاده نکن.

## تست‌های پیشنهادی قبل از Pull Request

Backend:

```powershell
cd backend
python manage.py check
python manage.py test
```

Frontend:

```powershell
cd frontend
npm ci
npm run typecheck
npm run build
```

جزئیات مشارکت در پروژه در [CONTRIBUTING.md](CONTRIBUTING.md) و الزامات امنیتی در [SECURITY.md](SECURITY.md) آمده است.
