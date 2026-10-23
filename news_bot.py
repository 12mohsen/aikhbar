"""بوت تلجرام: يجلب الأخبار من خلاصات RSS ويرسلها إلى قناتك.

التثبيت:   pip install requests feedparser
التشغيل:   BOT_TOKEN=xxx CHANNEL=@my_news_channel python news_bot.py
الجدولة:   شغّله كل 15 دقيقة عبر cron أو خدمة استضافة (Railway/Render/VPS)
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

# عدّل الخلاصات حسب مصادرك المفضلة
FEEDS = [
    "https://feeds.bbci.co.uk/arabic/business/rss.xml",
    "https://feeds.bbci.co.uk/arabic/rss.xml",
]


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False)


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
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
            title = html.escape(entry.get("title", ""))
            summary = html.escape(entry.get("summary", ""))[:300]
            link = entry.get("link", "")
            send(f"<b>{title}</b>\n\n{summary}\n\n{link}")
            seen.add(uid)
            sent += 1
            time.sleep(3)  # تفادي حدود الإرسال
            if sent >= MAX_PER_RUN:
                save_seen(seen)
                return
    save_seen(seen)


if __name__ == "__main__":
    main()
