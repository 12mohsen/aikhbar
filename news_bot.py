"""بوت تلجرام: يجلب الأخبار من خلاصات RSS ويرسل المطابق لمواضيعك فقط.

التثبيت:   pip install requests feedparser
التشغيل:   BOT_TOKEN=xxx CHANNEL=@my_news_channel python news_bot.py
"""
import html
import json
import os
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


def norm(s):
    """توحيد الحروف العربية لتطابق أدق (أ إ آ ← ا، ة ← ه، ى ← ي)."""
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return s.lower()


def match_topics(text):
    text = norm(text)
    if any(norm(w) in text for w in EXCLUDE):
        return []
    return [t for t in ACTIVE_TOPICS if any(norm(w) in text for w in TOPICS[t])]


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
        for entry in feedparser.parse(url).entries:
            uid = entry.get("id") or entry.get("link")
            if not uid or uid in seen:
                continue
            raw_title = entry.get("title", "")
            raw_summary = entry.get("summary", "")
            topics = match_topics(raw_title + " " + raw_summary) if ACTIVE_TOPICS else []
            if ACTIVE_TOPICS and not topics:
                seen.add(uid)  # غير مطابق: لا يُرسل ولا يُفحص مجدداً
                continue
            tags = " ".join("#" + t.replace(" ", "_") for t in topics)
            msg = (
                f"<b>{html.escape(raw_title)}</b>\n\n"
                f"{html.escape(raw_summary)[:300]}\n\n"
                f"{entry.get('link', '')}"
            )
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
