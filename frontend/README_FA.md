# راهنمای Frontend — AEGISVISION v1.5.0

فرانت‌اند با React، TypeScript و Vite اجرا می‌شود و رابط فارسی/انگلیسی با RTL/LTR را پشتیبانی می‌کند.

## نصب و اجرا در ویندوز

```cmd
cd C:\path\to\AegisVision\frontend
npm.cmd install
npm.cmd run dev
```

برای Build:

```cmd
npm.cmd run build
```

## صفحات مهم

- `/cameras` — ثبت، ویرایش و غیرفعال‌سازی دوربین‌ها.
- `/live-cameras` — پیش‌نمایش زنده، تشخیص و رهگیری، سلامت Worker، رویدادهای زنده و تعریف قوانین Zone/Line/Loitering.
- `/soc` — مرکز عملیات امنیتی (SOC).

زبان انتخاب‌شده در Local Storage مرورگر نگهداری می‌شود. ترجمه‌های جدید Live Camera در `src/i18n.tsx` قرار دارند.

## نکته فنی

پیش‌نمایش Live Camera با JPEG snapshotهای تازه‌شده از API کار می‌کند و WebRTC نیست. پردازش RTSP در Django worker انجام می‌شود؛ Vite فقط رابط کاربری را ارائه می‌کند.
