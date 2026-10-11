import os
import time
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def generate_feed():
    print("=== 特設ギャラリー RSS生成処理を開始します ===")
    
    url_file = "urls.txt"
    feed_file = "gallery_feed.xml"
    
    if not os.path.exists(url_file):
        print(f"エラー: {url_file} が見つかりません。処理を終了します。")
        return

    print(f"--- {url_file} を読み込み中 ---")
    with open(url_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    if not urls:
        print("URLが1つも登録されていません。")
        return
        
    print(f"合計 {len(urls)} 件のURLを処理します。")

    jst = timezone(timedelta(hours=9), 'JST')
    now_str = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    
    feed_xml = '<?xml version="1.0" encoding="utf-8"?>\n'
    feed_xml += '<feed xmlns="http://www.w3.org/2005/Atom">\n'
    feed_xml += '  <title>特設ギャラリー 画像コレクション</title>\n'
    feed_xml += f'  <updated>{now_str}</updated>\n'
    feed_xml += '  <id>urn:uuid:custom-gallery-feed-id</id>\n'
    feed_xml += '  <author><name>Gallery Bot</name></author>\n'

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for index, target_url in enumerate(urls, 1):
        print(f"\n[{index}/{len(urls)}] 処理中: {target_url}")
        
        try:
            print("  -> ページデータを取得中...")
            response = requests.get(target_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            page_title = soup.title.string.strip() if soup.title else f"Gallery {index}"
            print(f"  -> ページタイトル: {page_title}")
            
            image_urls = []
            print("  -> 画像URLを検索中...")
            for img in soup.find_all("img"):
                src = img.get("data-src") or img.get("src")
                if src:
                    full_url = urljoin(target_url, src)
                    if ".jpg" in full_url or ".png" in full_url or ".jpeg" in full_url or "image/" in full_url:
                        if full_url not in image_urls:
                            image_urls.append(full_url)
            
            if not image_urls:
                print("  -> 画像が見つかりませんでした。スキップします。")
                continue
                
            print(f"  -> {len(image_urls)} 枚の画像を発見！RSSエントリーを作成します。")
            
            content_html = ""
            for img_url in image_urls:
                # 画像自体をリンクにし、さらに下部にブラウザで開く用のテキストリンクを追加する
                content_html += f'<a href="{img_url}" target="_blank"><img src="{img_url}" style="max-width:100%; margin-bottom:5px;"></a><br/>\n'
                content_html += f'<a href="{img_url}" target="_blank" style="display:inline-block; margin-bottom:20px; font-size:14px; color:#0066cc; text-decoration:underline;">📥 原画をブラウザで開いて保存する</a><br/>\n'
                
            feed_xml += '  <entry>\n'
            feed_xml += f'    <title>{page_title}</title>\n'
            feed_xml += f'    <link href="{target_url}"/>\n'
            feed_xml += f'    <id>{target_url}</id>\n'
            feed_xml += f'    <updated>{now_str}</updated>\n'
            feed_xml += f'    <content type="html"><![CDATA[\n{content_html}    ]]></content>\n'
            feed_xml += '  </entry>\n'
            
        except Exception as e:
            print(f"  -> エラー発生: {target_url} の処理中に問題が起きました: {e}")
            
        time.sleep(2)

    feed_xml += '</feed>\n'

    print("\n--- RSSフィード（XML）を保存中 ---")
    with open(feed_file, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    print(f"保存完了: {feed_file} が生成されました。")
    print("=== すべての処理が正常に完了しました ===")

if __name__ == "__main__":
    generate_feed()
