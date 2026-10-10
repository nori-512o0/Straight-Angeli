import os
import re
import time
import json
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://straight-angeli.com"
NEWS_URL = f"{BASE_URL}/news/"
SCHEDULE_URL = f"{BASE_URL}/schedule/"
FEED_BASE_URL = "https://nori-512o0.github.io/Straight-Angeli/"  # ご自身のGitHub Pagesの公開URLに合わせて変更してください
STATE_FILE = "last_angeli_items.json"

def parse_date_to_iso(date_str):
    m = re.findall(r'\d+', date_str)
    if len(m) >= 3:
        year, month, day = m[0], m[1], m[2]
        hour = m[3] if len(m) >= 4 else "00"
        minute = m[4] if len(m) >= 5 else "00"
        second = m[5] if len(m) >= 6 else "00"
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}T{hour.zfill(2)}:{minute.zfill(2)}:{second.zfill(2)}+09:00"
    return datetime.now(timezone.utc).isoformat()

def main():
    print("=== [処理開始] Straight Angeli のRSS生成を開始します ===")
    os.makedirs("feeds", exist_ok=True)
    
    # 履歴データの読み込み
    state = {}
    if os.path.exists(STATE_FILE):
        print("-> [読込] 過去の履歴データを読み込みます...")
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            print(f"-> [警告] 履歴ファイルの読み込みに失敗しました: {e}")
    
    known_items = { entry["url"]: entry for entry in state.get("items", []) }
    new_items = []
    feed_updated = None

    # 1. Newsの取得
    print("[RSS取得中] Newsページにアクセスしています...")
    try:
        res = requests.get(NEWS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/news/" in href and href != "/news/":
                article_url = urljoin(BASE_URL, href)
                title = a.get_text(strip=True)
                if not title or title == "View All":
                    continue
                
                if article_url in known_items:
                    print(f"  -> [高速スキップ] 既知のニュース: {title}")
                    new_items.append(known_items[article_url])
                    if not feed_updated:
                        feed_updated = known_items[article_url]["updated"]
                    continue
                
                print(f"  -> [新規取得] ニュース: {title}")
                date_str = datetime.now().strftime("%Y.%m.%d")
                parent = a.parent
                if parent:
                    date_match = re.search(r'(\d{4}\.\d{2}\.\d{2})', parent.get_text())
                    if date_match:
                        date_str = date_match.group(1).replace(".", "-")
                
                entry_updated = parse_date_to_iso(date_str)
                if not feed_updated:
                    feed_updated = entry_updated
                
                content = f"<p><a href='{article_url}' target='_blank'>公式サイトでニュースを読む</a></p>"
                new_items.append({
                    "url": article_url,
                    "title": f"[NEWS] {title}",
                    "updated": entry_updated,
                    "content": content
                })
    except Exception as e:
        print(f"[エラー] News取得失敗: {e}")

    # 2. Scheduleの取得
    print("[RSS取得中] Scheduleページにアクセスしています...")
    try:
        res = requests.get(SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # スケジュール項目の抽出
        for box in soup.find_all(["div", "li", "article"]):
            text = box.get_text(strip=True)
            if "LIVE / EVENT" in text or "TV" in text or "RADIO" in text:
                title_tag = box.find(["h3", "h4", "p", "a"])
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if not title or len(title) < 3:
                    continue
                
                article_url = SCHEDULE_URL
                a_tag = box.find("a", href=True)
                if a_tag:
                    article_url = urljoin(BASE_URL, a_tag.get("href"))
                
                if article_url in known_items:
                    continue
                
                print(f"  -> [新規取得] スケジュール: {title}")
                date_str = datetime.now().strftime("%Y.%m.%d")
                date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
                if date_match:
                    date_str = date_match.group(1).replace(".", "-")
                
                entry_updated = parse_date_to_iso(date_str)
                if not feed_updated:
                    feed_updated = entry_updated
                
                content = f"<p>{escape(text)}</p><p><a href='{article_url}' target='_blank'>公式サイトでスケジュールを確認</a></p>"
                new_items.append({
                    "url": article_url + "#" + str(hash(title)),
                    "title": f"[SCHEDULE] {title}",
                    "updated": entry_updated,
                    "content": content
                })
    except Exception as e:
        print(f"[エラー] Schedule取得失敗: {e}")

    if not new_items:
        print("[スキップ] 新しい項目はありませんでした")
        return
        
    if not feed_updated:
        feed_updated = datetime.now(timezone.utc).isoformat()
        
    # Atom XMLの構築
    entries_xml = ""
    for item in new_items[:30]:  # 最大30件
        entries_xml += f"""
  <entry>
    <title>{escape(item['title'])}</title>
    <id>{escape(item['url'])}</id>
    <link href="{escape(item['url'])}"/>
    <updated>{escape(item['updated'])}</updated>
    <author>
      <name>Straight Angeli</name>
    </author>
    <content type="html"><![CDATA[
{item['content']}
    ]]></content>
  </entry>"""

    feed_filename = "feed_angeli.xml"
    feed_url = f"{FEED_BASE_URL}{feed_filename}"
    
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Straight Angeli ｜ News &amp; Schedule</title>
  <id>{escape(feed_url)}</id>
  <updated>{escape(feed_updated)}</updated>
  <link href="{escape(feed_url)}" rel="self"/>{entries_xml}
</feed>
"""
    
    with open(f"feeds/{feed_filename}", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[完了] フィードを生成しました (feeds/{feed_filename})")
    
    # 履歴を保存
    state["items"] = new_items
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
