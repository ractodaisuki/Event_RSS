#!/usr/bin/env python3
"""sources.json の情報源を巡回し、新しく見つかった項目を data/ に書き出す。

標準ライブラリだけで動く。GitHub Actions から毎日実行する想定。

出力:
  data/items.json  これまでに見つけた項目（first_seen から KEEP_DAYS 日だけ残す）
  data/new.json    直近 NEW_DAYS 日に見つかった項目（新しい順）。休日さがし dot はこれを読む
  data/status.json 情報源ごとの最終実行結果（失敗していないかの確認用）
  feed.xml         new.json と同じ内容の RSS（RSS リーダーで読む用）
"""
import hashlib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
JST = timezone(timedelta(hours=9))
KEEP_DAYS = 120
NEW_DAYS = 7
USER_AGENT = "Mozilla/5.0 (compatible; EventRSS/1.0; +https://github.com/ractodaisuki/Event_RSS)"
FEED_URL = "https://raw.githubusercontent.com/ractodaisuki/Event_RSS/main/feed.xml"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=30) as res:
        body = res.read()
        charset = res.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def item_id(source_id, key):
    return source_id + ":" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def parse_rss(src, body):
    root = ET.fromstring(body.encode("utf-8"))
    out = []
    # RSS 2.0
    for it in root.iter("item"):
        title = clean(it.findtext("title") or "")
        link = (it.findtext("link") or "").strip()
        published = None
        pub = it.findtext("pubDate")
        if pub:
            try:
                published = parsedate_to_datetime(pub).astimezone(JST).isoformat()
            except (TypeError, ValueError):
                pass
        if title and link:
            out.append({"title": title, "url": link, "published": published})
    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for it in root.iter(ns + "entry"):
        title = clean(it.findtext(ns + "title") or "")
        link_el = it.find(ns + "link")
        link = link_el.get("href", "") if link_el is not None else ""
        published = it.findtext(ns + "published") or it.findtext(ns + "updated")
        if title and link:
            out.append({"title": title, "url": link, "published": published})
    return out


def parse_links(src, body):
    pattern = re.compile(src["link_pattern"])
    seen = {}
    for href, inner in re.findall(r'<a\b[^>]*href="([^"#]+)"[^>]*>([\s\S]*?)</a>', body):
        url = urljoin(src["url"], html.unescape(href))
        if not pattern.match(url):
            continue
        title = clean(inner)
        # 同じ URL へのリンクが複数あるときは、いちばん長い文字列を題名にする
        if len(title) > len(seen.get(url, "")):
            seen[url] = title
    return [{"title": t or url, "url": u, "published": None} for u, t in seen.items()]


def parse_page(src, body):
    body = re.sub(r"<(script|style|noscript)[\s\S]*?</\1>", " ", body)
    text = clean(body)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return [{
        "title": src["name"] + " のページが更新されました",
        "url": src["url"],
        "published": None,
        "key": src["url"] + "#" + digest,
    }]


PARSERS = {"rss": parse_rss, "links": parse_links, "page": parse_page}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def write_feed(new_items, now):
    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = "関西イベント新着（Event_RSS）"
    ET.SubElement(ch, "link").text = "https://github.com/ractodaisuki/Event_RSS"
    ET.SubElement(ch, "description").text = "関西のアニメ・お笑い・映画などの情報源から、新しく見つかった項目"
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(now)
    for it in new_items:
        el = ET.SubElement(ch, "item")
        ET.SubElement(el, "title").text = "[" + it["source_name"] + "] " + it["title"]
        ET.SubElement(el, "link").text = it["url"]
        ET.SubElement(el, "guid", isPermaLink="false").text = it["id"]
        ET.SubElement(el, "category").text = it["genre"]
        ET.SubElement(el, "pubDate").text = format_datetime(datetime.fromisoformat(it["first_seen"]))
    ET.indent(rss)
    (ROOT / "feed.xml").write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="utf-8") + b"\n")


def main():
    now = datetime.now(JST).replace(microsecond=0)
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))["sources"]
    DATA.mkdir(exist_ok=True)
    items = load_json(DATA / "items.json", {})
    status = load_json(DATA / "status.json", {})
    first_run_sources = set()

    for src in sources:
        sid = src["id"]
        prev = status.get(sid, {})
        try:
            found = PARSERS[src["type"]](src, fetch(src["url"]))
        except Exception as e:  # 1 つの情報源の失敗で全体を止めない
            status[sid] = {**prev, "name": src["name"], "ok": False, "error": f"{type(e).__name__}: {e}"[:300],
                           "checked_at": now.isoformat()}
            print(f"NG  {sid}: {status[sid]['error']}", file=sys.stderr)
            continue

        # 初めて巡回する情報源は、今ある項目を「既知」として登録するだけにする（初回に大量の新着が出ないように）
        is_first = not prev.get("last_ok_at")
        if is_first:
            first_run_sources.add(sid)
        added = 0
        for f in found:
            iid = item_id(sid, f.get("key") or f["url"])
            if iid in items:
                items[iid]["last_seen"] = now.isoformat()
                continue
            items[iid] = {
                "id": iid,
                "source": sid,
                "source_name": src["name"],
                "genre": src.get("genre", ""),
                "title": f["title"][:300],
                "url": f["url"],
                "published": f.get("published"),
                "first_seen": now.isoformat(),
                "last_seen": now.isoformat(),
                "baseline": is_first,
            }
            added += 1
        status[sid] = {"name": src["name"], "ok": True, "error": None, "checked_at": now.isoformat(),
                       "last_ok_at": now.isoformat(), "found": len(found), "added": added}
        print(f"OK  {sid}: {len(found)} 件中 新規 {added} 件{'（初回のため既知として登録）' if is_first else ''}")

    # 古い項目を整理し、sources.json から消えた情報源の状態も消す
    keep_after = now - timedelta(days=KEEP_DAYS)
    items = {k: v for k, v in items.items() if datetime.fromisoformat(v["first_seen"]) >= keep_after}
    ids = {s["id"] for s in sources}
    status = {k: v for k, v in status.items() if k in ids}

    new_after = now - timedelta(days=NEW_DAYS)
    new_items = sorted(
        (v for v in items.values() if not v.get("baseline") and datetime.fromisoformat(v["first_seen"]) >= new_after),
        key=lambda v: (v["first_seen"], v["source"], v["title"]),
        reverse=True,
    )

    write_json(DATA / "items.json", dict(sorted(items.items())))
    write_json(DATA / "status.json", dict(sorted(status.items())))
    write_json(DATA / "new.json", {"generated_at": now.isoformat(), "days": NEW_DAYS, "items": new_items})
    write_feed(new_items, now)
    print(f"新着 {len(new_items)} 件（直近 {NEW_DAYS} 日）")


if __name__ == "__main__":
    main()
