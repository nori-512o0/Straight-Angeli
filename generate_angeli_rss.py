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
FEED_BASE_URL = "https://nori-512o0.github.io/Straight-Angeli/"
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

def parse_news_article(article_url):
    print(f"  -> [詳細取得中] {article_url}")
    try:
        res = requests.get(article_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 本文エリアを特定
        article_body = (
            soup.find("article") or 
            soup.find(class_=re.compile(r'detail|article|content|news-body|post', re.I)) or 
            soup.find("main")
        )
        
        if not article_body:
            article_body = soup.find("body")

        # 不要なナビゲーション、フッター、ヘッダー、サイドバー等を除外
        for unwanted in article_body.find_all(["nav", "footer", "header", "aside", "script", "style"]):
            unwanted.decompose()

        # 「SHARE」などのSNS共有エリアやアイコン群をクラス名やテキストから徹底的に探して削除
        for share_elem in article_body.find_all(class_=re.compile(r'share|social|sns|icon|button|back|top', re.I)):
            share_elem.decompose()

        # テキストで「SHARE」と書かれている見出しやその周辺も削除
        for text_elem in article_body.find_all(["h2", "h3", "h4", "div", "p"]):
            if "SHARE" in text_elem.get_text():
                text_elem.decompose()

        # 残った画像の絶対パス化と綺麗なHTML化
        for img in article_body.find_all("img"):
            src = img.get("src", "")
            if not src:
                img.decompose()
                continue
            
            img_url = urljoin(BASE_URL, src)
            lower_url = img_url.lower()
            
            # アイコンやロゴ等の不要な画像を追加で除外
            if any(keyword in lower_url for keyword in ["line", "icon", "share", "sns", "twitter", "facebook", "x_", "logo", "qr"]):
                img.decompose()
                continue

            safe_url = escape(img_url)
            img_html = f'<p><a href="{safe_url}"><img src="{safe_url}" alt="" style="max-width:100%;"></a></p>'
            img.replace_with(BeautifulSoup(img_html, "html.parser"))

        detailed_date = ""
        date_tag = soup.find(class_=re.compile(r'date|time', re.I))
        if date_tag:
            detailed_date = date_tag.get_text(strip=True)

        return str(article_body), detailed_date
    except Exception as e:
        print(f"     => [エラー] 詳細ページ取得失敗: {e}")
        return "<p>詳細ページの読み込みに失敗しました。</p>", ""

def main():
    print("=== [処理開始] Straight Angeli ニュースのRSS生成を開始します ===")
    os.makedirs("feeds", exist_ok=True)
    
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

    print("[RSS取得中] News一覧ページにアクセスしています...")
    try:
        res = requests.get(NEWS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        seen_urls = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/news/" in href and href.strip("/") != "news":
                article_url = urljoin(BASE_URL, href).split('?')[0]
                
                if "page" in article_url or "#" in href:
                    continue
                
                if article_url in seen_urls:
                    continue
                seen_urls.add(article_url)
                
                title = a.get_text(strip=True)
                if not title or title in ["View All", "次へ", "前へ", "NEWS", "Schedule", "ALL", "LIVE / EVENT", "RELEASE", "TV", "RADIO", "OTHER"] or len(title) < 4:
                    continue
                if title.isdigit() or re.match(r'^\d{4}[./]\d{2}[./]\d{2}$', title):
                    continue
                
                if article_url in known_items:
                    print(f"  -> [高速スキップ] 既知のニュース: {title}")
                    cached_item = known_items[article_url]
                    new_items.append(cached_item)
                    if not feed_updated:
                        feed_updated = cached_item["updated"]
                    continue
                
                print(f"  -> [新規検出] タイトル: {title}")
                content_html, detailed_date = parse_news_article(article_url)
                time.sleep(1)
                
                date_str = detailed_date
                if not date_str:
                    parent = a.parent
                    if parent:
                        date_match = re.search(r'(\d{4}[./]\d{1,2}[./]\d{1,2})', parent.get_text())
                        if date_match:
                            date_str = date_match.group(1)
                
                if not date_str:
                    date_str = datetime.now().strftime("%Y.%m.%d")
                
                entry_updated = parse_date_to_iso(date_str)
                if not feed_updated:
                    feed_updated = entry_updated
                
                new_items.append({
                    "url": article_url,
                    "title": title,
                    "updated": entry_updated,
                    "content": content_html
                })
                
                if len(new_items) >= 15:
                    break

    except Exception as e:
        print(f"[エラー] News一覧取得失敗: {e}")

    if not new_items:
        print("[スキップ] 有効なニュース記事はありませんでした")
        return
        
    if not feed_updated:
        feed_updated = datetime.now(timezone.utc).isoformat()
        
    entries_xml = ""
    for item in new_items:
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
  <title>Straight Angeli ｜ News</title>
  <id>{escape(feed_url)}</id>
  <updated>{escape(feed_updated)}</updated>
  <link href="{escape(feed_url)}" rel="self"/>{entries_xml}
</feed>
"""
    
    with open(f"feeds/{feed_filename}", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[完了] フィードを生成しました (feeds/{feed_filename})")
    
    state["items"] = new_items
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
