"""بوت تلجرام: يجلب الأخبار من خلاصات RSS ويرسل المطابق لمواضيعك فقط.

التثبيت:   pip install requests feedparser
التشغيل:   BOT_TOKEN=xxx CHANNEL=@my_news_channel python news_bot.py
"""
import html
import json
import os
import re
import time

import feedparser
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]      # من @BotFather
CHANNEL = os.environ["CHANNEL"]          # مثل @my_news_channel
SEEN_FILE = "seen.json"
MAX_PER_RUN = 5

# ---------------------------------------------------------------
# 1) المصادر: أضف أو احذف روابط RSS كما تريد
# ---------------------------------------------------------------
FEEDS = [
    "https://feeds.bbci.co.uk/arabic/rss.xml",
    "https://feeds.bbci.co.uk/arabic/business/rss.xml",
    "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
    "https://www.france24.com/ar/rss",
    "https://aawsat.com/feed",
    # خلاصة تتبّع (Google News): تُرسل كل نتائجها بدون فلتر المواضيع.
    # مثال: "https://news.google.com/rss/search?q=كوريا+الشمالية+when:1d&hl=ar&gl=SA&ceid=SA:ar",
]

# ---------------------------------------------------------------
# 2) المواضيع: عدّل الكلمات كما تشاء
# ---------------------------------------------------------------
TOPICS = {
    "اقتصاد": [
        "اقتصاد", "نفط", "اسعار", "بورصه", "اسهم", "بنك", "تضخم", "فائده",
        "الذهب", "الدولار", "عمله", "استثمار", "تجاره", "ميزانيه",
        "صندوق النقد", "اوبك", "ارباح", "اسواق", "عملات رقميه", "بيتكوين",
    ],
    "الشرق الأوسط": [
        "غزه", "فلسطين", "اسرائيل", "لبنان", "سوريا", "العراق", "اليمن",
        "ايران", "السعوديه", "مصر", "الاردن", "الخليج", "قطر", "الامارات",
        "الكويت", "عمان", "البحرين", "ليبيا", "السودان", "تونس", "الجزائر",
        "المغرب",
    ],
}

# المواضيع المفعّلة. اتركها فارغة [] لإرسال كل الأخبار بدون فلترة
ACTIVE_TOPICS = ["اقتصاد", "الشرق الأوسط"]

# أي خبر يحتوي إحدى هذه الكلمات لا يُرسل (اختياري)
EXCLUDE = []

# ---------------------------------------------------------------
# 3) إعدادات لوحة التحكم: إن وُجد ملف config.json فهو يتقدّم على ما سبق
# ---------------------------------------------------------------
try:
    with open("config.json", encoding="utf-8") as _f:
        _cfg = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError):
    _cfg = {}
FEEDS = _cfg.get("feeds", FEEDS)
TOPICS = _cfg.get("topics", TOPICS)
ACTIVE_TOPICS = [t for t in _cfg.get("active", ACTIVE_TOPICS) if t in TOPICS]
EXCLUDE = _cfg.get("exclude", EXCLUDE)
MAX_PER_RUN = int(_cfg.get("max_per_run", MAX_PER_RUN))


def norm(s):
    """توحيد الحروف العربية لتطابق أدق (أ إ آ ← ا، ة ← ه، ى ← ي)."""
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return s.lower()


PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ب", "ل", "ف")


def kw_hit(text, tokens, kw):
    """كلمة تبدأ بـ = تُطابَق ككلمة كاملة (مع السوابق مثل ال/ب/و)، وغير ذلك تُطابَق كجزء من النص."""
    kw = norm(kw)
    if kw.startswith("="):
        w = kw[1:]
        return any(
            t == w or any(t.startswith(p) and t[len(p):] == w for p in PREFIXES)
            for t in tokens
        )
    return kw in text


def match_topics(text):
    text = norm(text)
    tokens = re.findall(r"\w+", text)
    if any(kw_hit(text, tokens, w) for w in EXCLUDE):
        return []
    return [
        t for t in ACTIVE_TOPICS
        if any(kw_hit(text, tokens, w) for w in TOPICS[t])
    ]


def clean(s):
    """إزالة وسوم HTML والمسافات الزائدة من النص."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen)[-2000:], f, ensure_ascii=False)


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHANNEL, "text": text, "parse_mode": "HTML"},
        timeout=20,
    )
    r.raise_for_status()


def main():
    seen = load_seen()
    sent = 0
    for url in FEEDS:
        tracked = "news.google.com/rss/search" in url
        entries = feedparser.parse(url).entries
        if tracked:
            entries = entries[:3]  # آخر 3 أخبار فقط من خلاصات التتبّع
        for entry in entries:
            uid = entry.get("id") or entry.get("link")
            if not uid or uid in seen:
                continue
            raw_title = clean(entry.get("title", ""))
            raw_summary = clean(entry.get("summary", ""))
            if raw_summary.startswith(raw_title[:40]):
                raw_summary = ""  # الملخص يكرر العنوان
            use_filter = bool(ACTIVE_TOPICS) and not tracked
            topics = match_topics(raw_title + " " + raw_summary) if use_filter else []
            if use_filter and not topics:
                seen.add(uid)  # غير مطابق: لا يُرسل ولا يُفحص مجدداً
                continue
            tags = " ".join("#" + t.replace(" ", "_") for t in topics)
            parts = [f"<b>{html.escape(raw_title)}</b>"]
            if raw_summary:
                parts.append(html.escape(raw_summary[:300]))
            parts.append(entry.get("link", ""))
            msg = "\n\n".join(parts)
            if tags:
                msg += f"\n\n{tags}"
            send(msg)
            seen.add(uid)
            sent += 1
            time.sleep(3)  # تفادي حدود الإرسال
            if sent >= MAX_PER_RUN:
                save_seen(seen)
                return
    save_seen(seen)


if __name__ == "__main__":
    main()
