[app]

# --- مشخصات اپ ---
title = مانیز
package.name = moneyz
package.domain = org.moneyz
version = 1.0.0

# --- فایل‌ها ---
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json
source.exclude_dirs = .git,.github,.buildozer,bin,venv,__pycache__
# اگر فایل main.py در پوشه دیگری است، source.dir را عوض کنید

# --- وابستگی‌ها ---
# python-bidi باید نسخه 0.4.2 (پایتونی خالص) باشد؛ نسخه‌های جدید با Rust نوشته شده‌اند
# و روی python-for-android کامپایل نمی‌شوند.
# openssl برای اتصال HTTPS (قیمت طلا و دلار) لازم است.
requirements = hostpython3==3.11.5,python3==3.11.5,kivy==2.3.0,openssl,certifi,arabic-reshaper==3.0.0,python-bidi==0.4.2,jdatetime

# --- ظاهر ---
orientation = portrait
fullscreen = 0
# آیکن اپ: فایل icon.png (مربع، ترجیحاً 512x512) کنار main.py
icon.filename = %(source.dir)s/icon.png
# آیکن تطبیقی (اختیاری، برای اندروید 8 به بالا): دو فایل مربعی 512x512
# icon.adaptive_foreground.filename = %(source.dir)s/icon_fg.png
# icon.adaptive_background.filename = %(source.dir)s/icon_bg.png
# presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #0E1015

# --- اندروید ---
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.enable_androidx = True

# --- python-for-android ---
# نسخه پایدار p4a (پایتون 3.11 می‌سازد و با Kivy 2.3.0 سازگار است).
# بدون این خط، Buildozer شاخه master را می‌گیرد که الان پایتون 3.14 می‌سازد
# و Kivy 2.3.0 روی آن کامپایل نمی‌شود.
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
