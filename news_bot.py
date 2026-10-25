"""بوت تلجرام: يجلب الأخبار من خلاصات RSS ويرسل المطابق لمواضيعك فقط.

التثبيت:   pip install requests feedparser
التشغيل:   BOT_TOKEN=xxx CHANNEL=@my_news_channel python news_bot.py
"""
import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus, urlparse

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
BLOCKED = ("arabic.rt.com",)   # مصادر محجوبة لا يستخدمها البوت أبداً
FEEDS = [u for u in FEEDS if not any(b in u for b in BLOCKED)]
TOPICS = _cfg.get("topics", TOPICS)
ACTIVE_TOPICS = [t for t in _cfg.get("active", ACTIVE_TOPICS) if t in TOPICS]
EXCLUDE = _cfg.get("exclude", EXCLUDE)
# خلاصات التتبّع أولاً: المصادر العامة غزيرة وكانت تلتهم حصة الإرسال قبل
# أن يصل دور التتبّع، فلا يظهر الخبر الذي تتابعه أصلاً. الترتيب ثابت الباقي.
FEEDS.sort(key=lambda u: "news.google.com/rss/search" not in u)
MAX_PER_RUN = int(_cfg.get("max_per_run", MAX_PER_RUN))
# الفاصل الزمني بين كل إرسال بالدقائق (0 = كل تشغيل كما تحدده الجدولة)
INTERVAL_MINUTES = int(_cfg.get("interval_minutes", 0) or 0)
# التشغيل اليدوي من Actions أو من زر الحفظ يتجاوز الفاصل دائماً
FORCE = os.environ.get("FORCE", "").strip().lower() in ("1", "true", "yes")

# شكل الرسالة: short = عنوان مختصر + مصدر + توقيع القناة، full = عنوان + ملخص + وسوم
STYLE = {
    "mode": "full",
    "signature": "",          # مثل @newsMO1
    "show_source": True,      # سطر «المصدر: ...» برابط الخبر الأصلي
    "breaking_words": ["عاجل", "انفجار", "اغتيال", "زلزال", "غارات", "قصف"],
    "tz": 3,                  # فرق التوقيت عن UTC (السعودية = 3)
    "quiet": {"enabled": False, "start": "00:00", "end": "06:00", "allow_breaking": True},
    "digest": {"enabled": False, "time": "07:00", "count": 8},
    "auto_hashtags": True,    # إضافة هاشتاجات تلقائياً (تفيد في بحث تلجرام)
    "hashtags": ["#أخبار"],   # هاشتاجات ثابتة تُضاف لكل خبر
    "keyword_tags": True,     # هاشتاج للكلمات التي طابقت الخبر (مثل #السعودية)
    "max_tags": 6,
}
STYLE.update(_cfg.get("style") or {})


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


def is_excluded(text):
    """كلمات الاستبعاد تُفحص لكل خبر: التتبّع يتجاوز فلتر المواضيع لا الاستبعاد."""
    if not EXCLUDE:
        return False
    t = norm(text)
    tokens = re.findall(r"\w+", t)
    return any(kw_hit(t, tokens, w) for w in EXCLUDE)


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
    """إزالة وسوم HTML والنصوص البرمجية الزائدة (مثل taxonomy/term/2) والمسافات."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\S*(?:taxonomy/term|node)/\d+\S*", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---- اسم المصدر الحقيقي ----
SITE_NAMES = {
    "bbc.co.uk": "BBC عربي", "bbci.co.uk": "BBC عربي", "bbc.com": "BBC عربي",
    "aljazeera.net": "الجزيرة نت", "france24.com": "فرانس 24",
    "aawsat.com": "الشرق الأوسط", "alquds.co.uk": "القدس العربي",
    "skynewsarabia.com": "سكاي نيوز عربية",
    "alarabiya.net": "العربية", "arabicpost.net": "عربي بوست",
    "youm7.com": "اليوم السابع", "dw.com": "DW عربية",
    "aa.com.tr": "الأناضول", "independentarabia.com": "اندبندنت عربية",
    "argaam.com": "أرقام",
}
_TECH = re.compile(r"taxonomy|term/|node/|\.xml|\.rss|\.php|https?:|rss|feed|[?=&]", re.I)


def looks_technical(name):
    return (not name) or "/" in name or len(name) > 40 or bool(_TECH.search(name))


def host_of(url):
    return (urlparse(url or "").netloc.lower().split(":")[0]).removeprefix("www.")


def source_label(entry_source, feed_title, link):
    """يختار اسماً نظيفاً للمصدر ويتجاهل النصوص التقنية."""
    if entry_source and not looks_technical(entry_source):
        return entry_source  # ناشر الخبر الحقيقي (يأتي من Google News)
    host = host_of(link)
    for dom, name in SITE_NAMES.items():
        if host == dom or host.endswith("." + dom):
            return name
    if feed_title and not looks_technical(feed_title):
        return feed_title
    if host and host != "news.google.com":
        return host
    return ""


def load_seen():
    """يعيد قاموساً مرتباً بحسب الإضافة (مفاتيحه معرّفات الأخبار وعناوينها)."""
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return dict.fromkeys(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


HISTORY_HOURS = 48      # عمر سجلات التاريخ H: قبل حذفها
MAX_IDS = 4000          # أقصى عدد معرّفات/مفاتيح منع التكرار المحفوظة


def save_seen(seen):
    """يحفظ المعرّفات وسجلات التاريخ بحدّين منفصلين.

    سجلات H: ثقيلة وكانت تزاحم معرّفات الأخبار على نفس الحد، فيُطرد معرّف
    لخبر ما زال في الخلاصة فيُرسل مرة ثانية. الآن لكلٍّ حدّه.
    """
    cutoff = time.time() - HISTORY_HOURS * 3600
    ids, hist = [], []
    for k in seen:
        if k.startswith("H:"):
            try:
                if json.loads(k[2:]).get("ts", 0) >= cutoff:
                    hist.append(k)
            except json.JSONDecodeError:
                pass
        else:
            ids.append(k)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(ids[-MAX_IDS:] + hist, f, ensure_ascii=False)


def last_run(seen):
    """وقت آخر تشغيل فعلي للبوت (مخزَّن في seen.json كمفتاح R:)."""
    ts = 0
    for k in seen:
        if k.startswith("R:"):
            try:
                ts = max(ts, int(k[2:]))
            except ValueError:
                pass
    return ts


def mark_run(seen):
    """يسجّل وقت هذا التشغيل ويحذف الطابع القديم حتى لا تتراكم."""
    for k in [k for k in seen if k.startswith("R:")]:
        del seen[k]
    seen["R:" + str(int(time.time()))] = None


# ---- منع تكرار نفس الخبر من مصادر مختلفة ----
STOP = {"ان", "في", "من", "على", "الى", "عن", "مع", "ما", "هذا", "هذه", "بعد",
        "قبل", "التي", "الذي", "ثم", "قال", "تقرير", "عاجل", "حول", "ضد"}


def title_tokens(title):
    out = set()
    for w in re.findall(r"\w+", norm(title)):
        if w.startswith("ال") and len(w) > 4:
            w = w[2:]
        if len(w) > 4 and w[0] in "وبلف":
            w = w[1:]
        if len(w) >= 3 and w not in STOP:
            out.add(w)
    return frozenset(out)


def is_dup(tok, recent):
    if len(tok) < 3:
        return False
    for r in recent:
        i = len(tok & r)
        if i and (i / len(tok | r) >= 0.5
                  or (i >= 3 and i / min(len(tok), len(r)) >= 0.75)):
            return True
    return False


def send(text, preview=True):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHANNEL, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": not preview},
        timeout=20,
    )
    r.raise_for_status()


def local_now():
    return datetime.now(timezone.utc) + timedelta(hours=float(STYLE.get("tz", 3)))


def _minutes(hhmm, default):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return default


def in_quiet(now):
    q = STYLE.get("quiet") or {}
    if not q.get("enabled"):
        return False
    a, b = _minutes(q.get("start"), 0), _minutes(q.get("end"), 360)
    t = now.hour * 60 + now.minute
    return (a <= t < b) if a <= b else (t >= a or t < b)


def is_urgent(title):
    return any(norm(w) in norm(title) for w in STYLE.get("breaking_words", []))


def add_history(seen, title, link, src, urgent):
    rec = {"ts": int(time.time()), "t": title, "l": link, "s": src, "u": urgent}
    seen["H:" + json.dumps(rec, ensure_ascii=False)] = None


def recent_history(seen, hours=24):
    cutoff = time.time() - hours * 3600
    out = []
    for k in seen:
        if k.startswith("H:"):
            try:
                r = json.loads(k[2:])
            except json.JSONDecodeError:
                continue
            if r.get("ts", 0) >= cutoff:
                out.append(r)
    return out


def maybe_digest(seen, now):
    """ملخص يومي: يُرسل مرة واحدة بعد وقت الملخص، من أخبار آخر 24 ساعة."""
    d = STYLE.get("digest") or {}
    if not d.get("enabled"):
        return
    key = "D:" + now.strftime("%Y-%m-%d")
    if key in seen or now.hour * 60 + now.minute < _minutes(d.get("time"), 420):
        return
    seen[key] = None
    items = recent_history(seen)
    if not items:
        return
    items.sort(key=lambda r: (not r.get("u"), -r["ts"]))  # العاجل أولاً ثم الأحدث
    lines, size = [], 0
    for i, r in enumerate(items[: int(d.get("count", 8))], 1):
        t = re.sub(r"^\s*عاجل\s*[:|\-–]*\s*", "", r["t"])
        mark = "🔴 " if r.get("u") else ""
        line = f'{i}. {mark}<a href="{html.escape(r["l"], quote=True)}">{html.escape(t)}</a>'
        if size + len(line) > 3500:
            break
        lines.append(line)
        size += len(line) + 2
    msg = "☀️ <b>أبرز أخبار آخر 24 ساعة</b>\n\n" + "\n\n".join(lines)
    if STYLE.get("signature"):
        msg += "\n\n" + html.escape(STYLE["signature"])
    send(msg, preview=False)
    print("تم إرسال الملخص اليومي")


def to_tag(text):
    """يحوّل نصاً إلى هاشتاج صالح في تلجرام (بدون مسافات أو رموز)."""
    words = re.sub(r"[^\w\s]", " ", text or "").split()
    t = "_".join(words)
    return "#" + t if len(t) >= 2 and not t.isdigit() else ""


def matched_keywords(text, topics, limit=2):
    n = norm(text)
    tokens = re.findall(r"\w+", n)
    found = []
    for t in topics:
        for kw in TOPICS.get(t, []):
            if kw_hit(n, tokens, kw):
                label = kw.lstrip("=")
                if label not in found:
                    found.append(label)
            if len(found) >= limit:
                return found
    return found


def build_tags(title, summary, topics, urgent, tracked_query):
    if not STYLE.get("auto_hashtags", True):
        return ""
    fixed = list(STYLE.get("hashtags") or [])
    cands = []
    if urgent:
        cands.append("عاجل")
    cands += fixed[:1]                      # هاشتاج القناة الأساسي أولاً
    cands += list(topics)
    if STYLE.get("keyword_tags", True):
        cands += matched_keywords(title + " " + summary, topics)
    if tracked_query:
        cands.append(tracked_query)
    cands += fixed[1:]                      # بقية الثابتة إن بقي مجال
    tags = []
    for c in cands:
        t = to_tag(c)
        if t and t not in tags:
            tags.append(t)
    return " ".join(tags[: int(STYLE.get("max_tags", 6))])


def build_message(title, summary, link, source, topics, tracked_query=""):
    if STYLE.get("mode") == "short":
        urgent = any(norm(w) in norm(title) for w in STYLE.get("breaking_words", []))
        title = re.sub(r"^\s*عاجل\s*[:|\-–]*\s*", "", title)
        tags = build_tags(title, summary, topics, urgent, tracked_query)
        if urgent:
            parts = ["🔴 <b>عاجل | " + html.escape(title) + "</b>"]
        else:
            parts = ["<b>" + html.escape(title) + "</b>"]
        if STYLE.get("show_source", True) and link:
            label = "🔗 قراءة الخبر من " + (source or "المصدر")
            parts.append(f'<a href="{html.escape(link, quote=True)}">{html.escape(label)}</a>')
        if tags:
            parts.append(html.escape(tags))
        if STYLE.get("signature"):
            parts.append(html.escape(STYLE["signature"]))
        return "\n\n".join(parts)
    parts = [f"<b>{html.escape(title)}</b>"]
    if summary:
        parts.append(html.escape(summary[:300]))
    parts.append(link)
    msg = "\n\n".join(parts)
    urgent = any(norm(w) in norm(title) for w in STYLE.get("breaking_words", []))
    tags = build_tags(title, summary, topics, urgent, tracked_query)
    return msg + (f"\n\n{html.escape(tags)}" if tags else "")


def main():
    seen = load_seen()
    if INTERVAL_MINUTES and not FORCE:
        waited = (time.time() - last_run(seen)) / 60
        if waited < INTERVAL_MINUTES:
            print(f"تخطٍّ: مضى {waited:.0f} دقيقة من أصل {INTERVAL_MINUTES} "
                  f"دقيقة (الفاصل المختار). لم يُرسل شيء.")
            return
    mark_run(seen)
    recent = [frozenset(k[2:].split()) for k in seen if k.startswith("T:")][-300:]
    sent = 0
    now = local_now()
    quiet = in_quiet(now)
    print(f"الوقت المحلي: {now:%H:%M} | ساعات الهدوء: {'نعم' if quiet else 'لا'}")
    print(f"المواضيع المفعّلة: {ACTIVE_TOPICS or 'الكل (بدون فلتر)'} | "
          f"عدد المصادر: {len(FEEDS)} | أقصى إرسال: {MAX_PER_RUN}")
    for url in FEEDS:
        tracked = "news.google.com/rss/search" in url
        tq = ""
        if tracked:
            m = re.search(r"[?&]q=([^&]*)", url)
            if m:
                tq = re.sub(r"\s*when:\S+", "", unquote_plus(m.group(1))).strip()
        d = feedparser.parse(url)
        feed_info = getattr(d, "feed", None) or {}
        feed_title = clean(feed_info.get("title", ""))
        entries = d.entries
        if not entries:
            print(f"[تحذير] لا أخبار من: {url[:70]} ({getattr(d, 'bozo_exception', 'فارغ')})")
            continue
        if tracked:
            entries = entries[:3]  # آخر 3 أخبار فقط من خلاصات التتبّع
        st = {"كل": len(entries), "جديد": 0, "غير مطابق": 0, "مكرر": 0, "صمت": 0, "أُرسل": 0}
        for entry in entries:
            uid = entry.get("id") or entry.get("link")
            if not uid or uid in seen:
                continue
            st["جديد"] += 1
            raw_title = clean(entry.get("title", ""))
            ent_src = clean((entry.get("source") or {}).get("title", ""))
            if ent_src and raw_title.endswith(" - " + ent_src):
                raw_title = raw_title[: -len(ent_src) - 3].strip()
            src = source_label(ent_src, feed_title, entry.get("link", ""))
            if src and raw_title.endswith(" - " + src):
                raw_title = raw_title[: -len(src) - 3].strip()
            raw_summary = clean(entry.get("summary", ""))
            if raw_summary.startswith(raw_title[:40]):
                raw_summary = ""  # الملخص يكرر العنوان
            full_text = raw_title + " " + raw_summary
            if is_excluded(full_text):
                seen[uid] = None  # يحتوي كلمة مستبعدة
                st["غير مطابق"] += 1
                continue
            use_filter = bool(ACTIVE_TOPICS) and not tracked
            topics = match_topics(full_text) if use_filter else []
            if use_filter and not topics:
                seen[uid] = None  # غير مطابق: لا يُرسل ولا يُفحص مجدداً
                st["غير مطابق"] += 1
                continue
            tok = title_tokens(raw_title)
            if is_dup(tok, recent):
                seen[uid] = None  # نفس الخبر وصل سابقاً من مصدر آخر
                st["مكرر"] += 1
                continue
            urgent = is_urgent(raw_title)
            if quiet and not (urgent and (STYLE.get("quiet") or {}).get("allow_breaking", True)):
                seen[uid] = None  # وقت هدوء: لا يُنشر الخبر العادي
                st["صمت"] += 1
                continue
            msg = build_message(raw_title, raw_summary, entry.get("link", ""), src, topics, tq)
            send(msg, preview=STYLE.get("mode") != "short")
            seen[uid] = None
            if len(tok) >= 3:
                recent.append(tok)
                seen["T:" + " ".join(sorted(tok))] = None
            add_history(seen, raw_title, entry.get("link", ""), src, urgent)
            sent += 1
            st["أُرسل"] += 1
            time.sleep(3)  # تفادي حدود الإرسال
            if sent >= MAX_PER_RUN:
                break
        print(f"{url[:60]} -> {st}")
        if sent >= MAX_PER_RUN:
            print("وصل الحد الأقصى للإرسال في هذا التشغيل")
            break
    try:
        maybe_digest(seen, now)
    except Exception as e:  # لا نُفشل التشغيل بسبب الملخص
        print(f"[تحذير] تعذّر إرسال الملخص: {e}")
    save_seen(seen)
    print(f"تم إرسال {sent} خبر")


if __name__ == "__main__":
    main()
