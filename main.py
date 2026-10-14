# -*- coding: utf-8 -*-
"""
اپلیکیشن ساده مدیریت مالی شخصی با Kivy
(تراکنش‌های درآمد/هزینه + بدهکاری و طلبکاری)

نصب وابستگی‌ها:
    pip install kivy arabic-reshaper python-bidi
    pip install jdatetime        # اختیاری: نمایش تاریخ شمسی
    pip install certifi          # برای اتصال HTTPS (دریافت قیمت طلا و دلار)

اجرا:
    python Moneyz_app.py

فونت فارسی:
    اگر فونت مناسبی روی سیستم پیدا نشود، فایل Vazirmatn-Regular.ttf را کنار
    همین اسکریپت بگذارید یا مسیر فونت را در متغیر محیطی APP_FONT بدهید.
"""
import json
import os
import re
import textwrap
import unicodedata
import uuid
from datetime import datetime

from kivy.config import Config
from kivy.utils import platform

# اندازه پنجره شبیه موبایل (فقط روی دسکتاپ)
if platform in ("win", "linux", "macosx"):
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "760")

from kivy.app import App
from kivy.core.text import Label as CoreLabel, LabelBase
from kivy.lang import Builder
from kivy.network.urlrequest import UrlRequest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import (
    BooleanProperty, ListProperty, NumericProperty, StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

# ---------------------------------------------------------------------------
# پشتیبانی از متن فارسی (اتصال حروف + راست‌به‌چپ)
# ---------------------------------------------------------------------------
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def fa(text):
        return get_display(arabic_reshaper.reshape(str(text)))
except ImportError:  # اگر کتابخانه‌ها نصب نبودند، متن خام نمایش داده می‌شود
    def fa(text):
        return str(text)

def fa_wrap(text, width=30):
    """شکل‌دهی متن فارسی چندخطی؛ هر خط جدا شکل می‌گیرد تا شکستن خط درست باشد"""
    lines = []
    for para in str(text).splitlines() or [""]:
        for line in textwrap.wrap(para, width=width) or [""]:
            lines.append(fa(line))
    return "\n".join(lines)


try:
    import jdatetime

    def today_str():
        return jdatetime.date.today().strftime("%Y/%m/%d")
except ImportError:
    jdatetime = None

    def today_str():
        return datetime.now().strftime("%Y-%m-%d")


def parse_date(text):
    """
    متن تاریخ (سال/ماه/روز) را بررسی می‌کند.
    خروجی: (رشته تاریخ هم‌قالب today_str, تاریخ میلادی) یا None اگر نامعتبر بود.
    """
    t = str(text).translate(DIGIT_MAP).strip()
    parts = re.split(r"[/\-.\s]+", t)
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    y, m, d = (int(p) for p in parts)
    if not 1000 <= y <= 9999:
        return None
    try:
        if jdatetime is not None:
            jd = jdatetime.date(y, m, d)
            return jd.strftime("%Y/%m/%d"), jd.togregorian()
        gd = datetime(y, m, d).date()
        return gd.strftime("%Y-%m-%d"), gd
    except (ValueError, OverflowError):
        return None


def find_font():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("APP_FONT", ""),
        os.path.join(here, "Vazirmatn-Regular.ttf"),
        os.path.join(here, "Vazir.ttf"),
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Tahoma.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/system/fonts/NotoNaskhArabic-Regular.ttf",
        "/system/fonts/DroidSansArabic.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


FONT_PATH = find_font()
if FONT_PATH:
    # جایگزین کردن فونت پیش‌فرض Kivy (Roboto) برای همه ویجت‌ها
    LabelBase.register(name="Roboto", fn_regular=FONT_PATH, fn_bold=FONT_PATH)
else:
    print("هشدار: فونت فارسی پیدا نشد؛ متن‌ها ممکن است درست نمایش داده نشوند.")

# ---------------------------------------------------------------------------
# داده‌ها
# ---------------------------------------------------------------------------
# گزینه‌ای که کاربر با انتخابش، نام دسته‌بندی را خودش می‌نویسد
CUSTOM_KEY = "دستی"

CATEGORIES = {
    "expense": [CUSTOM_KEY, "خوراک", "حمل و نقل", "مسکن", "قبوض", "سلامت", "تفریح", "خرید"],
    "income": [CUSTOM_KEY, "حقوق", "پروژه", "هدیه", "سرمایه گذاری"],
}

# owe  = من بدهکارم (باید به دیگری بپردازم)
# owed = من طلبکارم (دیگری باید به من بپردازد)
DEBT_KIND_LABEL = {"owe": "بدهکارم", "owed": "طلبکارم"}

# عنوان تراکنشی که هنگام تسویه خودکار ثبت می‌شود
SETTLE_PREFIX = {"owe": "پرداخت بدهی", "owed": "دریافت طلب"}

GREEN = [0.30, 0.82, 0.58, 1]
RED = [0.98, 0.47, 0.50, 1]

# تبدیل ارقام فارسی/عربی به انگلیسی
DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# قیمت زنده طلا و دلار (TGJU)
PRICE_URL = (
    "https://call3.tgju.org/ajax.json"
    "?rev=uBzqzJh2FszXrrMz0Xra7C8v7ONYWIssyGpnFbF88F3loeWm6fz7qAmdRNsn"
)
PRICE_INTERVAL = 30          # ثانیه
GOLD_KEY = "geram18"         # هر گرم طلای ۱۸ عیار
DOLLAR_KEY = "price_dollar_rl"  # دلار بازار آزاد

try:
    import certifi
    CA_FILE = certifi.where()
except ImportError:
    CA_FILE = None


class Storage:
    """ذخیره‌سازی ساده لیست‌ها در فایل JSON"""

    def __init__(self, path):
        self.path = path

    def load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, items):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# ویجت‌ها
# ---------------------------------------------------------------------------
class FlatButton(Button):
    """دکمه تخت با گوشه گرد (رنگ پس‌زمینه با bg_color)"""
    bg_color = ListProperty([0.38, 0.56, 0.98, 1])
    radius = NumericProperty(dp(14))


class SegButton(ToggleButton):
    """دکمه انتخاب در نوار دوحالته (sel_color = رنگ حالت انتخاب‌شده)"""
    sel_color = ListProperty([0.38, 0.56, 0.98, 1])


def _is_rtl_text(text):
    """جهت پاراگراف: اولین حرف قوی (فارسی/عربی → راست‌به‌چپ)"""
    for ch in text:
        d = unicodedata.bidirectional(ch)
        if d in ("R", "AL"):
            return True
        if d == "L":
            return False
    return False


def _measure(text, font_name, font_size):
    try:
        return CoreLabel(font_name=font_name, font_size=font_size).get_extents(text)[0]
    except Exception:
        return 0


class FlatInput(TextInput):
    """
    ورودی متن با ظاهر مینیمال و پشتیبانی درست از فارسی.

    TextInput خود Kivy نه حروف فارسی را به هم وصل می‌کند و نه متن راست‌به‌چپ را
    درست می‌چیند. برای همین متن خود TextInput نامرئی می‌شود (ولی همچنان ورودی
    کیبورد را می‌گیرد و text همیشه متن اصلی/منطقی است) و به‌جایش یک Label
    متن را با fa() شکل می‌دهد و نمایش می‌دهد. مکان‌نما هم دستی رسم می‌شود.

    محدودیت: ویرایش فقط از انتهای متن انجام می‌شود (مکان‌نما همیشه آخر متن است).
    """
    text_color = ListProperty([0.93, 0.94, 0.97, 1])
    hint_color = ListProperty([0.55, 0.58, 0.66, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._view = Label(
            size_hint=(None, None), valign="middle", shorten=True, markup=False,
        )
        self.add_widget(self._view)
        with self.canvas.after:
            self._caret_color = Color(0, 0, 0, 0)
            self._caret = Rectangle(size=(dp(1.5), dp(16)))
        self._caret_on = True
        self._blink_ev = None

        self.bind(
            text=self._on_text, hint_text=self._sync, pos=self._sync, size=self._sync,
            font_size=self._sync, font_name=self._sync, halign=self._sync,
            padding=self._sync, text_color=self._sync, hint_color=self._sync,
            cursor_color=self._sync,
        )
        self.bind(focus=self._on_focus_blink)
        self.bind(cursor=self._schedule_cursor_end)
        self.bind(selection_text=self._drop_selection)
        self._sync()

    # ---- نمایش ----
    def _on_text(self, *_):
        self._caret_on = True
        self._sync()

    def _sync(self, *_):
        v = self._view
        raw = self.text
        pl, pr = self.padding[0], self.padding[2]
        avail = max(self.width - pl - pr, 0)
        x0 = self.x + pl

        if raw:
            shown = fa(raw)
            v.color = self.text_color
            rtl = _is_rtl_text(raw)
        else:
            shown = self.hint_text or ""  # hint_text از قبل با app.t شکل داده شده
            v.color = self.hint_color
            rtl = False

        v.font_name = self.font_name
        v.font_size = self.font_size
        v.text = shown
        v.size = (avail, self.height)
        v.text_size = (avail, self.height)
        v.pos = (x0, self.y)
        v.halign = self.halign
        # اگر متن بلند شد، ابتدای متن بریده شود تا انتهای آن (محل تایپ) دیده شود
        v.shorten_from = "right" if rtl else "left"

        # ---- محل مکان‌نما ----
        tw = min(_measure(shown, self.font_name, self.font_size), avail) if raw else 0
        ha = self.halign
        if ha == "auto":
            ha = "right" if rtl else "left"
        if ha == "center":
            left = x0 + (avail - tw) / 2
        elif ha == "right":
            left = x0 + avail - tw
        else:
            left = x0
        cx = left if rtl else left + tw
        cw = self._caret.size[0]
        cx = min(max(cx, x0), x0 + avail - cw)
        lh = self.line_height
        self._caret.size = (cw, lh)
        self._caret.pos = (cx, self.center_y - lh / 2)
        self._update_caret_alpha()

    def _update_caret_alpha(self):
        c = self.cursor_color
        on = self.focus and self._caret_on
        self._caret_color.rgba = (c[0], c[1], c[2], 1 if on else 0)

    def _on_focus_blink(self, _w, focused):
        if self._blink_ev is not None:
            self._blink_ev.cancel()
            self._blink_ev = None
        self._caret_on = True
        if focused:
            self._blink_ev = Clock.schedule_interval(self._blink, 0.5)
        self._update_caret_alpha()

    def _blink(self, _dt):
        self._caret_on = not self._caret_on
        self._update_caret_alpha()

    # ---- مکان‌نما همیشه انتهای متن ----
    def _schedule_cursor_end(self, *_):
        Clock.schedule_once(self._cursor_to_end, 0)

    def _cursor_to_end(self, *_):
        end = self.get_cursor_from_index(len(self.text))
        if tuple(self.cursor) != tuple(end):
            self.cursor = end

    def _drop_selection(self, *_):
        if self.selection_text:
            self.cancel_selection()


class AmountInput(FlatInput):
    """ورودی مبلغ: فقط رقم می‌پذیرد و ارقام فارسی را به انگلیسی تبدیل می‌کند"""

    def insert_text(self, substring, from_undo=False):
        substring = substring.translate(DIGIT_MAP)
        substring = "".join(ch for ch in substring if ch.isdigit())
        return super().insert_text(substring, from_undo=from_undo)


class DateInput(FlatInput):
    """ورودی تاریخ: فقط رقم و جداکننده می‌پذیرد"""

    def insert_text(self, substring, from_undo=False):
        substring = substring.translate(DIGIT_MAP)
        substring = "".join(ch for ch in substring if ch.isdigit() or ch in "/-.")
        return super().insert_text(substring, from_undo=from_undo)


class SummaryCard(BoxLayout):
    title = StringProperty()
    value = StringProperty("0")
    value_color = ListProperty([1, 1, 1, 1])


class TransactionRow(BoxLayout):
    tx_id = StringProperty()
    category_text = StringProperty()
    date_text = StringProperty()
    amount_text = StringProperty()
    amount_color = ListProperty([1, 1, 1, 1])
    has_note = BooleanProperty(False)


class DebtRow(BoxLayout):
    debt_id = StringProperty()
    person_text = StringProperty()
    sub_text = StringProperty()
    amount_text = StringProperty()
    amount_color = ListProperty([1, 1, 1, 1])
    settle_text = StringProperty()
    settled = BooleanProperty(False)
    has_note = BooleanProperty(False)


KV = """
#:import FadeTransition kivy.uix.screenmanager.FadeTransition

# ---------------------------------------------------------------------------
# پالت رنگ (یک‌جا تعریف شده تا تغییرش آسان باشد)
# ---------------------------------------------------------------------------
#:set C_BG       [0.055, 0.063, 0.082, 1]
#:set C_SURFACE  [0.094, 0.106, 0.137, 1]
#:set C_SURFACE2 [0.135, 0.150, 0.195, 1]
#:set C_TEXT     [0.93, 0.94, 0.97, 1]
#:set C_MUTED    [0.55, 0.58, 0.66, 1]
#:set C_ACCENT   [0.38, 0.56, 0.98, 1]
#:set C_GREEN    [0.30, 0.82, 0.58, 1]
#:set C_RED      [0.98, 0.47, 0.50, 1]

# ===========================================================================
# اجزای پایه
# ===========================================================================
<FlatButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    opacity: 0.65 if self.state == 'down' else 1
    canvas.before:
        Color:
            rgba: root.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [root.radius]

# دکمه حذف (ضربدر با خط رسم می‌شود تا به گلیف فونت وابسته نباشد)
<CloseButton@FlatButton>:
    bg_color: 0, 0, 0, 0
    size_hint_x: None
    width: dp(38)
    canvas.after:
        Color:
            rgba: C_MUTED
        Line:
            points: self.center_x - dp(5), self.center_y - dp(5), self.center_x + dp(5), self.center_y + dp(5)
            width: dp(1.3)
            cap: 'round'
        Line:
            points: self.center_x - dp(5), self.center_y + dp(5), self.center_x + dp(5), self.center_y - dp(5)
            width: dp(1.3)
            cap: 'round'

# دکمه کوچک گرد «i» برای نمایش توضیحات
<InfoButton@FlatButton>:
    text: 'i'
    font_size: sp(13)
    size_hint_x: None
    size_hint_y: None
    width: dp(26)
    height: dp(26)
    radius: dp(13)
    pos_hint: {'center_y': 0.5}

# دکمه کوچک گرد با آیکون تقویم (با خط رسم می‌شود)
<DateButton@FlatButton>:
    size_hint_x: None
    size_hint_y: None
    width: dp(26)
    height: dp(26)
    radius: dp(13)
    pos_hint: {'center_y': 0.5}
    bg_color: C_ACCENT[:3] + [0.16]
    canvas.after:
        Color:
            rgba: C_ACCENT
        Line:
            rounded_rectangle: self.center_x - dp(6), self.center_y - dp(6), dp(12), dp(11), dp(2)
            width: dp(1)
        Line:
            points: self.center_x - dp(6), self.center_y + dp(2), self.center_x + dp(6), self.center_y + dp(2)
            width: dp(1)
        Line:
            points: self.center_x - dp(3), self.center_y + dp(4), self.center_x - dp(3), self.center_y + dp(7)
            width: dp(1)
            cap: 'round'
        Line:
            points: self.center_x + dp(3), self.center_y + dp(4), self.center_x + dp(3), self.center_y + dp(7)
            width: dp(1)
            cap: 'round'

<SegButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    font_size: sp(14)
    color: root.sel_color if self.state == 'down' else C_MUTED
    canvas.before:
        Color:
            rgba: (root.sel_color[:3] + [0.16]) if self.state == 'down' else [0, 0, 0, 0]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(11)]

<NavTab@ToggleButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    font_size: sp(14)
    color: C_ACCENT if self.state == 'down' else C_MUTED
    canvas.before:
        Color:
            rgba: C_ACCENT[:3] + [1 if self.state == 'down' else 0]
        RoundedRectangle:
            pos: self.center_x - dp(14), self.top - dp(3)
            size: dp(28), dp(3)
            radius: [dp(2)]

<FlatInput>:
    multiline: False
    write_tab: False
    halign: 'right'
    background_normal: ''
    background_active: ''
    background_color: 0, 0, 0, 0
    # متن/hint/مکان‌نمای خود TextInput نامرئی است؛ نمایش را FlatInput._view انجام می‌دهد
    foreground_color: 0, 0, 0, 0
    disabled_foreground_color: 0, 0, 0, 0
    hint_text_color: 0, 0, 0, 0
    text_color: C_TEXT
    hint_color: C_MUTED
    cursor_color: C_ACCENT
    cursor_width: 0
    selection_color: 0, 0, 0, 0
    use_bubble: False
    use_handles: False
    font_size: sp(15)
    padding: dp(16), max((self.height - self.line_height) / 2, 0)
    canvas.before:
        Color:
            rgba: C_SURFACE
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
        Color:
            rgba: C_ACCENT[:3] + [0.9 if self.focus else 0]
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(14)
            width: dp(1.1)

<AmountInput>:
    input_type: 'number'

<FlatSpinnerOption@SpinnerOption>:
    size_hint_y: None
    height: dp(46)
    background_normal: ''
    background_down: ''
    background_color: C_SURFACE2
    color: C_TEXT
    font_size: sp(14)
    opacity: 0.7 if self.state == 'down' else 1

<FlatSpinner@Spinner>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    option_cls: 'FlatSpinnerOption'
    color: C_TEXT
    font_size: sp(14)
    canvas.before:
        Color:
            rgba: C_SURFACE
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
    canvas.after:
        Color:
            rgba: C_MUTED
        Triangle:
            points: self.x + dp(12), self.center_y + dp(2), self.x + dp(20), self.center_y + dp(2), self.x + dp(16), self.center_y - dp(3)

# ---- کارت خلاصه (بدون پس‌زمینه؛ داخل کارت اصلی قرار می‌گیرد) ----
<SummaryCard>:
    orientation: 'vertical'
    spacing: dp(2)
    Label:
        text: root.title
        font_size: sp(12)
        color: C_MUTED
        text_size: self.size
        halign: 'right'
        valign: 'bottom'
    Label:
        text: root.value
        font_size: sp(16)
        color: root.value_color
        text_size: self.size
        halign: 'right'
        valign: 'top'
        shorten: True
        shorten_from: 'left'

# ===========================================================================
# ردیف‌های لیست (راست‌به‌چپ: متن سمت راست، عملیات سمت چپ)
# ===========================================================================
<TransactionRow>:
    orientation: 'vertical'
    size_hint_y: None
    height: dp(76)
    padding: dp(12), dp(6), dp(18), dp(6)
    canvas.before:
        Color:
            rgba: C_SURFACE
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]
    # خط اول: مبلغ (چپ) و دسته‌بندی (راست)
    BoxLayout:
        Label:
            text: root.amount_text
            size_hint_x: None
            width: dp(140)
            font_size: sp(16)
            color: root.amount_color
            text_size: self.size
            halign: 'left'
            valign: 'middle'
        Label:
            text: root.category_text
            font_size: sp(15)
            color: C_TEXT
            text_size: self.size
            halign: 'right'
            valign: 'middle'
            shorten: True
            shorten_from: 'left'
    # خط دوم: دکمه‌ها (چپ) و تاریخ (راست)
    BoxLayout:
        spacing: dp(6)
        CloseButton:
            width: dp(30)
            on_release: app.root.delete_transaction(root.tx_id)
        InfoButton:
            color: C_ACCENT if root.has_note else C_MUTED
            bg_color: C_ACCENT[:3] + [0.16 if root.has_note else 0.06]
            on_release: app.root.show_note(root.tx_id)
        DateButton:
            on_release: app.root.edit_date('tx', root.tx_id)
        Label:
            text: root.date_text
            font_size: sp(11)
            color: C_MUTED
            text_size: self.size
            halign: 'right'
            valign: 'middle'

<DebtRow>:
    orientation: 'vertical'
    size_hint_y: None
    height: dp(76)
    padding: dp(12), dp(6), dp(18), dp(6)
    opacity: 0.45 if root.settled else 1
    canvas.before:
        Color:
            rgba: C_SURFACE
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]
    # خط اول: مبلغ (چپ) و نام شخص (راست)
    BoxLayout:
        Label:
            text: root.amount_text
            size_hint_x: None
            width: dp(140)
            font_size: sp(16)
            color: root.amount_color
            text_size: self.size
            halign: 'left'
            valign: 'middle'
        Label:
            text: root.person_text
            font_size: sp(15)
            color: C_TEXT
            text_size: self.size
            halign: 'right'
            valign: 'middle'
            shorten: True
            shorten_from: 'left'
    # خط دوم: دکمه‌ها (چپ) و توضیح نوع/تاریخ (راست)
    BoxLayout:
        spacing: dp(6)
        CloseButton:
            width: dp(30)
            on_release: app.root.delete_debt(root.debt_id)
        InfoButton:
            color: C_ACCENT if root.has_note else C_MUTED
            bg_color: C_ACCENT[:3] + [0.16 if root.has_note else 0.06]
            on_release: app.root.show_debt_note(root.debt_id)
        DateButton:
            on_release: app.root.edit_date('debt', root.debt_id)
        FlatButton:
            text: root.settle_text
            size_hint_x: None
            size_hint_y: None
            width: dp(56)
            height: dp(26)
            pos_hint: {'center_y': 0.5}
            font_size: sp(12)
            radius: dp(13)
            color: C_ACCENT
            bg_color: C_ACCENT[:3] + [0.16]
            on_release: app.root.toggle_settled(root.debt_id)
        Label:
            text: root.sub_text
            font_size: sp(11)
            color: C_MUTED
            text_size: self.size
            halign: 'right'
            valign: 'middle'

# ===========================================================================
# صفحه اصلی
# ===========================================================================
<MoneyzRoot>:
    orientation: 'vertical'
    canvas.before:
        Color:
            rgba: C_BG
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: dp(20), dp(18), dp(20), 0
        spacing: dp(14)

        # ---- سربرگ ----
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(46)
            Label:
                text: app.t("مانیز")
                font_size: sp(21)
                color: C_TEXT
                text_size: self.size
                halign: 'right'
                valign: 'middle'
            BoxLayout:
                size_hint_y: None
                height: dp(16)
                spacing: dp(8)
                Label:
                    text: root.dollar_text
                    font_size: sp(12)
                    color: C_MUTED
                    text_size: self.size
                    halign: 'left'
                    valign: 'top'
                    shorten: True
                    shorten_from: 'left'
                Label:
                    text: root.gold_text
                    font_size: sp(12)
                    color: C_MUTED
                    text_size: self.size
                    halign: 'right'
                    valign: 'top'
                    shorten: True
                    shorten_from: 'left'

        ScreenManager:
            id: sm
            transition: FadeTransition(duration=0.12)

            # =============== بخش ۱: درآمد و هزینه ===============
            Screen:
                name: 'tx'
                BoxLayout:
                    orientation: 'vertical'
                    spacing: dp(12)

                    # کارت اصلی: مانده + درآمد/هزینه
                    BoxLayout:
                        orientation: 'vertical'
                        size_hint_y: None
                        height: dp(140)
                        padding: dp(22), dp(16)
                        spacing: dp(2)
                        canvas.before:
                            Color:
                                rgba: C_SURFACE
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [dp(24)]
                        Label:
                            text: app.t("مانده")
                            font_size: sp(13)
                            color: C_MUTED
                            size_hint_y: None
                            height: dp(20)
                            text_size: self.size
                            halign: 'right'
                            valign: 'middle'
                        Label:
                            text: root.balance_text
                            font_size: sp(32)
                            color: root.balance_color
                            text_size: self.size
                            halign: 'right'
                            valign: 'middle'
                            shorten: True
                            shorten_from: 'left'
                        BoxLayout:
                            size_hint_y: None
                            height: dp(42)
                            spacing: dp(12)
                            SummaryCard:
                                title: app.t("هزینه")
                                value: root.expense_text
                                value_color: C_RED
                            SummaryCard:
                                title: app.t("درآمد")
                                value: root.income_text
                                value_color: C_GREEN

                    # انتخاب نوع تراکنش
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        padding: dp(4)
                        spacing: dp(4)
                        canvas.before:
                            Color:
                                rgba: C_SURFACE
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [dp(14)]
                        SegButton:
                            text: app.t("درآمد")
                            group: 'tx_type'
                            allow_no_selection: False
                            sel_color: C_GREEN
                            on_release: root.set_type('income')
                        SegButton:
                            text: app.t("هزینه")
                            group: 'tx_type'
                            state: 'down'
                            allow_no_selection: False
                            sel_color: C_RED
                            on_release: root.set_type('expense')

                    # مبلغ + دسته‌بندی
                    BoxLayout:
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height

                        # مبلغ + دسته‌بندی
                        BoxLayout:
                            size_hint_y: None
                            height: dp(48)
                            spacing: dp(10)
                            AmountInput:
                                id: amount
                                hint_text: app.t("مبلغ")
                            FlatSpinner:
                                id: category
                                size_hint_x: 0.38
                                on_text: root.on_category_change(self.text)

                        # نام دسته‌بندی دستی (فقط وقتی «دستی» انتخاب شده نمایش داده می‌شود)
                        BoxLayout:
                            size_hint_y: None
                            height: dp(58) if root.use_custom_cat else 0
                            padding: 0, dp(10), 0, 0
                            opacity: 1 if root.use_custom_cat else 0
                            disabled: not root.use_custom_cat
                            FlatInput:
                                id: custom_category
                                hint_text: app.t("نام دسته بندی را بنویسید")

                    # توضیحات + افزودن
                    BoxLayout:
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(10)
                        FlatButton:
                            text: app.t("افزودن")
                            size_hint_x: 0.28
                            font_size: sp(14)
                            bg_color: C_ACCENT
                            on_release: root.add_transaction()
                        FlatInput:
                            id: note
                            hint_text: app.t("توضیحات (اختیاری)")

                    Label:
                        text: app.t("تراکنش ها")
                        font_size: sp(13)
                        color: C_MUTED
                        size_hint_y: None
                        height: dp(22)
                        text_size: self.size
                        halign: 'right'
                        valign: 'bottom'

                    Label:
                        text: app.t("هنوز تراکنشی ثبت نشده است")
                        font_size: sp(13)
                        color: C_MUTED
                        opacity: 0 if root.has_items else 1
                        size_hint_y: None
                        height: 0 if root.has_items else dp(36)

                    RecycleView:
                        id: rv
                        viewclass: 'TransactionRow'
                        bar_width: dp(2)
                        bar_color: 1, 1, 1, 0.25
                        bar_inactive_color: 1, 1, 1, 0.08
                        RecycleBoxLayout:
                            orientation: 'vertical'
                            default_size: None, dp(76)
                            default_size_hint: 1, None
                            size_hint_y: None
                            height: self.minimum_height
                            spacing: dp(8)

            # =============== بخش ۲: بدهکاری و طلبکاری ===============
            Screen:
                name: 'debt'
                BoxLayout:
                    orientation: 'vertical'
                    spacing: dp(12)

                    # کارت اصلی: خالص + بدهکاری/طلبکاری
                    BoxLayout:
                        orientation: 'vertical'
                        size_hint_y: None
                        height: dp(140)
                        padding: dp(22), dp(16)
                        spacing: dp(2)
                        canvas.before:
                            Color:
                                rgba: C_SURFACE
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [dp(24)]
                        Label:
                            text: app.t("خالص")
                            font_size: sp(13)
                            color: C_MUTED
                            size_hint_y: None
                            height: dp(20)
                            text_size: self.size
                            halign: 'right'
                            valign: 'middle'
                        Label:
                            text: root.net_text
                            font_size: sp(32)
                            color: root.net_color
                            text_size: self.size
                            halign: 'right'
                            valign: 'middle'
                            shorten: True
                            shorten_from: 'left'
                        BoxLayout:
                            size_hint_y: None
                            height: dp(42)
                            spacing: dp(12)
                            SummaryCard:
                                title: app.t("جمع بدهکاری")
                                value: root.owe_text
                                value_color: C_RED
                            SummaryCard:
                                title: app.t("جمع طلبکاری")
                                value: root.owed_text
                                value_color: C_GREEN

                    # انتخاب نوع
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        padding: dp(4)
                        spacing: dp(4)
                        canvas.before:
                            Color:
                                rgba: C_SURFACE
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [dp(14)]
                        SegButton:
                            text: app.t("طلبکارم")
                            group: 'debt_kind'
                            allow_no_selection: False
                            sel_color: C_GREEN
                            on_release: root.set_debt_kind('owed')
                        SegButton:
                            text: app.t("بدهکارم")
                            group: 'debt_kind'
                            state: 'down'
                            allow_no_selection: False
                            sel_color: C_RED
                            on_release: root.set_debt_kind('owe')

                    # نام شخص + مبلغ
                    BoxLayout:
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(10)
                        AmountInput:
                            id: debt_amount
                            hint_text: app.t("مبلغ")
                            size_hint_x: 0.42
                        FlatInput:
                            id: person
                            hint_text: app.t("نام شخص")

                    # توضیحات + افزودن
                    BoxLayout:
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(10)
                        FlatButton:
                            text: app.t("افزودن")
                            size_hint_x: 0.28
                            font_size: sp(14)
                            bg_color: C_ACCENT
                            on_release: root.add_debt()
                        FlatInput:
                            id: debt_note
                            hint_text: app.t("توضیحات (اختیاری)")

                    Label:
                        text: app.t("بدهی ها و طلب ها")
                        font_size: sp(13)
                        color: C_MUTED
                        size_hint_y: None
                        height: dp(22)
                        text_size: self.size
                        halign: 'right'
                        valign: 'bottom'

                    Label:
                        text: app.t("هنوز موردی ثبت نشده است")
                        font_size: sp(13)
                        color: C_MUTED
                        opacity: 0 if root.has_debts else 1
                        size_hint_y: None
                        height: 0 if root.has_debts else dp(36)

                    RecycleView:
                        id: debt_rv
                        viewclass: 'DebtRow'
                        bar_width: dp(2)
                        bar_color: 1, 1, 1, 0.25
                        bar_inactive_color: 1, 1, 1, 0.08
                        RecycleBoxLayout:
                            orientation: 'vertical'
                            default_size: None, dp(76)
                            default_size_hint: 1, None
                            size_hint_y: None
                            height: self.minimum_height
                            spacing: dp(8)

    # ---- نوار پایین برای جابه‌جایی بین بخش‌ها ----
    BoxLayout:
        size_hint_y: None
        height: dp(58)
        canvas.before:
            Color:
                rgba: C_SURFACE
            Rectangle:
                pos: self.pos
                size: self.size
            Color:
                rgba: 1, 1, 1, 0.05
            Rectangle:
                pos: self.x, self.top - dp(1)
                size: self.width, dp(1)
        NavTab:
            text: app.t("بدهکاری و طلبکاری")
            group: 'nav'
            allow_no_selection: False
            on_release: sm.current = 'debt'
        NavTab:
            text: app.t("درآمد و هزینه")
            group: 'nav'
            state: 'down'
            allow_no_selection: False
            on_release: sm.current = 'tx'
"""


class MoneyzRoot(BoxLayout):
    # خلاصه درآمد/هزینه
    income_text = StringProperty("0")
    expense_text = StringProperty("0")
    balance_text = StringProperty("0")
    balance_color = ListProperty(GREEN)
    has_items = BooleanProperty(False)
    use_custom_cat = BooleanProperty(False)  # نمایش فیلد دسته‌بندی دستی

    # خلاصه بدهکاری/طلبکاری
    owe_text = StringProperty("0")
    owed_text = StringProperty("0")
    net_text = StringProperty("0")
    net_color = ListProperty(GREEN)
    has_debts = BooleanProperty(False)

    # قیمت زنده طلا و دلار (سربرگ)
    gold_text = StringProperty("")
    dollar_text = StringProperty("")

    tx_type = "expense"
    debt_kind = "owe"
    transactions = []
    debts = []
    store = None
    debt_store = None
    _cat_map = {}

    # قیمت‌ها (تومان)؛ None یعنی هنوز دریافت نشده
    _gold = None
    _dollar = None
    _price_req = None
    _price_ev = None

    # ---- راه‌اندازی ----
    def setup(self, store, debt_store):
        self.store = store
        self.debt_store = debt_store
        self.transactions = store.load()
        self.debts = debt_store.load()
        self.set_type("expense")
        self.refresh()
        self.refresh_debts()
        self.start_price_updates()

    # =====================================================================
    # قیمت زنده طلا و دلار
    # =====================================================================
    def start_price_updates(self):
        self.gold_text = fa("در حال دریافت قیمت...")
        self.fetch_prices()
        self._price_ev = Clock.schedule_interval(self.fetch_prices, PRICE_INTERVAL)

    def fetch_prices(self, *_):
        # اگر درخواست قبلی هنوز در جریان است، درخواست تازه نفرست
        if self._price_req is not None and not self._price_req.is_finished:
            return
        self._price_req = UrlRequest(
            PRICE_URL,
            on_success=self._on_prices,
            on_failure=self._on_price_error,
            on_error=self._on_price_error,
            req_headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=10,
            ca_file=CA_FILE,
        )

    @staticmethod
    def _rial_to_toman(value):
        """'260,552,000' (ریال) → 26055200 (تومان)"""
        clean = str(value).replace(",", "").strip()
        return int(round(float(clean) / 10))

    def _on_prices(self, req, result):
        try:
            if isinstance(result, (bytes, bytearray)):
                result = result.decode("utf-8")
            if isinstance(result, str):
                result = json.loads(result)
            current = result["current"]
            gold = self._rial_to_toman(current[GOLD_KEY]["p"])
            dollar = self._rial_to_toman(current[DOLLAR_KEY]["p"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._on_price_error(req, None)
            return
        self._gold, self._dollar = gold, dollar
        self._show_prices()

    def _on_price_error(self, req, error):
        # اگر قیمت قبلی داریم همان را نگه می‌داریم؛ وگرنه پیام خطا
        if self._gold is None:
            self.gold_text = fa("خطا در دریافت قیمت")
            self.dollar_text = ""

    def _show_prices(self):
        self.gold_text = fa(f"طلا ۱۸: {self._gold:,} تومان")
        self.dollar_text = fa(f"دلار: {self._dollar:,} تومان")

    # =====================================================================
    # درآمد و هزینه
    # =====================================================================
    def set_type(self, tx_type):
        self.tx_type = tx_type
        self._cat_map = {fa(c): c for c in CATEGORIES[tx_type]}
        values = list(self._cat_map.keys())
        self.ids.category.values = values
        self.ids.category.text = values[0]

    def on_category_change(self, text):
        """با انتخاب «دستی» فیلد نوشتن نام دسته‌بندی نمایش داده می‌شود"""
        custom = self._cat_map.get(text) == CUSTOM_KEY
        self.use_custom_cat = custom
        if custom:
            Clock.schedule_once(
                lambda dt: setattr(self.ids.custom_category, "focus", True), 0.1
            )

    def add_transaction(self):
        raw = self.ids.amount.text.strip()
        if not raw or int(raw) <= 0:
            self.show_message("خطا", "یک مبلغ معتبر وارد کنید.")
            return

        category = self._cat_map.get(self.ids.category.text, "سایر")
        if category == CUSTOM_KEY:
            category = self.ids.custom_category.text.strip()
            if not category:
                self.show_message("خطا", "نام دسته بندی را وارد کنید.")
                return
        note = self.ids.note.text.strip()
        self.transactions.append({
            "id": uuid.uuid4().hex,
            "type": self.tx_type,
            "amount": int(raw),
            "category": category,
            "note": note,
            "date": today_str(),
            "ts": datetime.now().isoformat(),
        })
        self.store.save(self.transactions)
        self.ids.amount.text = ""
        self.ids.note.text = ""
        self.ids.custom_category.text = ""
        self.refresh()

    def delete_transaction(self, tx_id):
        self.transactions = [t for t in self.transactions if t["id"] != tx_id]
        self.store.save(self.transactions)
        self.refresh()

    def refresh(self):
        items = sorted(self.transactions, key=lambda t: t["ts"], reverse=True)

        self.ids.rv.data = [
            {
                "tx_id": t["id"],
                "category_text": fa(t["category"]),
                "date_text": t["date"],
                "amount_text": ("+" if t["type"] == "income" else "-") + f"{t['amount']:,}",
                "amount_color": GREEN if t["type"] == "income" else RED,
                "has_note": bool(t.get("note")),
            }
            for t in items
        ]

        income = sum(t["amount"] for t in items if t["type"] == "income")
        expense = sum(t["amount"] for t in items if t["type"] == "expense")
        balance = income - expense

        self.income_text = f"{income:,}"
        self.expense_text = f"{expense:,}"
        self.balance_text = f"{balance:,}"
        self.balance_color = GREEN if balance >= 0 else RED
        self.has_items = bool(items)

    # =====================================================================
    # بدهکاری و طلبکاری
    # =====================================================================
    def set_debt_kind(self, kind):
        self.debt_kind = kind

    def add_debt(self):
        person = self.ids.person.text.strip()
        raw = self.ids.debt_amount.text.strip()

        if not person:
            self.show_message("خطا", "نام شخص را وارد کنید.")
            return
        if not raw or int(raw) <= 0:
            self.show_message("خطا", "یک مبلغ معتبر وارد کنید.")
            return

        self.debts.append({
            "id": uuid.uuid4().hex,
            "kind": self.debt_kind,
            "person": person,
            "note": self.ids.debt_note.text.strip(),
            "amount": int(raw),
            "date": today_str(),
            "ts": datetime.now().isoformat(),
            "settled": False,
        })
        self.debt_store.save(self.debts)
        self.ids.person.text = ""
        self.ids.debt_amount.text = ""
        self.ids.debt_note.text = ""
        self.refresh_debts()

    def toggle_settled(self, debt_id):
        """
        تسویه بدهی → یک تراکنش هزینه (پرداخت کردم)
        تسویه طلب  → یک تراکنش درآمد (دریافت کردم)
        برگشت از تسویه → همان تراکنش خودکار حذف می‌شود.
        """
        debt = next((d for d in self.debts if d["id"] == debt_id), None)
        if debt is None:
            return

        debt["settled"] = not debt.get("settled", False)

        if debt["settled"]:
            self.transactions.append({
                "id": uuid.uuid4().hex,
                "type": "expense" if debt["kind"] == "owe" else "income",
                "amount": debt["amount"],
                "category": f"{SETTLE_PREFIX[debt['kind']]}: {debt['person']}",
                "note": debt.get("note", ""),
                "date": today_str(),
                "ts": datetime.now().isoformat(),
                "debt_id": debt_id,  # پیوند تراکنش به بدهی
            })
        else:
            self.transactions = [
                t for t in self.transactions if t.get("debt_id") != debt_id
            ]

        self.store.save(self.transactions)
        self.debt_store.save(self.debts)
        self.refresh()
        self.refresh_debts()

    def delete_debt(self, debt_id):
        self.debts = [d for d in self.debts if d["id"] != debt_id]
        self.debt_store.save(self.debts)
        self.refresh_debts()

    def refresh_debts(self):
        # جدیدترین‌ها اول؛ تسویه‌شده‌ها آخر لیست
        items = sorted(self.debts, key=lambda d: d["ts"], reverse=True)
        items = sorted(items, key=lambda d: d.get("settled", False))

        rows = []
        for d in items:
            settled = d.get("settled", False)
            status = "  " + fa("تسویه شد") if settled else ""
            rows.append({
                "debt_id": d["id"],
                "person_text": fa(d["person"]),
                "sub_text": fa(DEBT_KIND_LABEL[d["kind"]]) + "  " + d["date"] + status,
                "amount_text": f"{d['amount']:,}",
                "amount_color": RED if d["kind"] == "owe" else GREEN,
                "settle_text": fa("برگشت") if settled else fa("تسویه"),
                "settled": settled,
                "has_note": bool(d.get("note")),
            })
        self.ids.debt_rv.data = rows

        # فقط موارد تسویه‌نشده در جمع‌ها حساب می‌شوند
        open_items = [d for d in self.debts if not d.get("settled", False)]
        owe = sum(d["amount"] for d in open_items if d["kind"] == "owe")
        owed = sum(d["amount"] for d in open_items if d["kind"] == "owed")
        net = owed - owe

        self.owe_text = f"{owe:,}"
        self.owed_text = f"{owed:,}"
        self.net_text = f"{net:,}"
        self.net_color = GREEN if net >= 0 else RED
        self.has_debts = bool(items)

    # =====================================================================
    # نمایش توضیحات تراکنش
    # =====================================================================
    def _make_popup(self, title, content, size_hint):
        return Popup(
            title=fa(title),
            content=content,
            size_hint=size_hint,
            background="",
            background_color=[0.094, 0.106, 0.137, 1],
            separator_height=0,
            title_color=[0.93, 0.94, 0.97, 1],
            title_align="center",
            overlay_color=[0, 0, 0, 0.6],
        )

    def _open_note(self, note):
        note = (note or "").strip()

        label = Label(
            text=fa_wrap(note) if note else fa("توضیحاتی ثبت نشده است"),
            font_size=sp(15),
            color=[0.93, 0.94, 0.97, 1] if note else [0.55, 0.58, 0.66, 1],
            size_hint_y=None,
            halign="right",
            valign="top",
        )
        label.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        label.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))

        scroll = ScrollView(bar_width=dp(2))
        scroll.add_widget(label)

        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(16))
        content.add_widget(scroll)
        btn = FlatButton(
            text=fa("بستن"), size_hint_y=None, height=dp(46),
            bg_color=[0.135, 0.150, 0.195, 1],
        )
        content.add_widget(btn)

        popup = self._make_popup("توضیحات", content, (0.86, 0.4))
        btn.bind(on_release=popup.dismiss)
        popup.open()

    def show_note(self, tx_id):
        tx = next((t for t in self.transactions if t["id"] == tx_id), None)
        if tx is not None:
            self._open_note(tx.get("note"))

    def show_debt_note(self, debt_id):
        debt = next((d for d in self.debts if d["id"] == debt_id), None)
        if debt is not None:
            self._open_note(debt.get("note"))

    # =====================================================================
    # تغییر دستی تاریخ (برای تراکنش‌ها و بدهی/طلب‌ها)
    # =====================================================================
    def edit_date(self, kind, item_id):
        items = self.transactions if kind == "tx" else self.debts
        item = next((i for i in items if i["id"] == item_id), None)
        if item is None:
            return

        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        content.add_widget(Label(
            text=fa("تاریخ جدید را وارد کنید"), font_size=sp(14),
            color=[0.55, 0.58, 0.66, 1], size_hint_y=None, height=dp(24),
        ))
        field = DateInput(
            text=item.get("date", ""), hint_text=today_str(),
            size_hint_y=None, height=dp(48), halign="center",
        )
        content.add_widget(field)

        error = Label(
            text="", font_size=sp(12), color=RED,
            size_hint_y=None, height=dp(34), halign="center", valign="middle",
        )
        error.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        content.add_widget(error)

        buttons = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        cancel = FlatButton(text=fa("انصراف"), bg_color=[0.135, 0.150, 0.195, 1])
        save = FlatButton(text=fa("ذخیره"))
        buttons.add_widget(cancel)
        buttons.add_widget(save)
        content.add_widget(buttons)

        popup = self._make_popup("تغییر تاریخ", content, (0.86, 0.48))

        def do_save(*_):
            parsed = parse_date(field.text)
            if parsed is None:
                error.text = fa("تاریخ معتبر نیست. نمونه درست:") + "\n" + today_str()
                return
            norm, greg = parsed
            try:
                old_time = datetime.fromisoformat(item["ts"]).time()
            except (KeyError, ValueError):
                old_time = datetime.now().time()
            item["date"] = norm
            # ts هم هماهنگ می‌شود تا ترتیب لیست با تاریخ جدید درست بماند
            item["ts"] = datetime.combine(greg, old_time).isoformat()
            if kind == "tx":
                self.store.save(self.transactions)
                self.refresh()
            else:
                self.debt_store.save(self.debts)
                self.refresh_debts()
            popup.dismiss()

        save.bind(on_release=do_save)
        cancel.bind(on_release=popup.dismiss)
        field.bind(on_text_validate=do_save)
        popup.bind(on_open=lambda *_: setattr(field, "focus", True))
        popup.open()

    # =====================================================================
    # پیام خطا
    # =====================================================================
    def show_message(self, title, message):
        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(16))
        content.add_widget(Label(
            text=fa(message), font_size=sp(15), color=[0.93, 0.94, 0.97, 1],
        ))
        btn = FlatButton(text=fa("باشه"), size_hint_y=None, height=dp(46))
        content.add_widget(btn)
        popup = Popup(
            title=fa(title),
            content=content,
            size_hint=(0.84, 0.32),
            background="",
            background_color=[0.094, 0.106, 0.137, 1],
            separator_height=0,
            title_color=[0.93, 0.94, 0.97, 1],
            title_align="center",
            overlay_color=[0, 0, 0, 0.6],
        )
        btn.bind(on_release=popup.dismiss)
        popup.open()


class MoneyzApp(App):
    title = "مانیز"

    def t(self, text):
        """شکل‌دهی متن فارسی برای استفاده در فایل KV"""
        return fa(text)

    def build(self):
        self.store = Storage(os.path.join(self.user_data_dir, "transactions.json"))
        self.debt_store = Storage(os.path.join(self.user_data_dir, "debts.json"))
        Window.clearcolor = (0.055, 0.063, 0.082, 1)
        Builder.load_string(KV)
        return MoneyzRoot()

    def on_start(self):
        self.root.setup(self.store, self.debt_store)


if __name__ == "__main__":
    MoneyzApp().run()
