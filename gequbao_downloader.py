#!/usr/bin/env python3
"""
歌曲宝 (gequbao.net) 音乐下载器
用法:
  python gequbao_downloader.py <歌曲ID或URL>
  python gequbao_downloader.py search <关键词>
  python gequbao_downloader.py batch <ID1,ID2,...>
  加 --hd 获取高品质版本
示例:
  python gequbao_downloader.py 3322385
  python gequbao_downloader.py search Vertigo
  python gequbao_downloader.py search "Montagem Bandidio" --hd
  python gequbao_downloader.py batch 3322385,1255744
"""

import sys
import os
import re
import json
import time
import html
import http.cookiejar
import urllib.request
import urllib.parse
import ssl

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class Session:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_ctx),
            urllib.request.HTTPCookieProcessor(self.cj),
        )
        self.opener.open(
            urllib.request.Request("https://www.gequbao.net/", headers={"User-Agent": UA}),
            timeout=10,
        )

    def get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.gequbao.net/"})
        return self.opener.open(req, timeout=20).read().decode("utf-8", errors="ignore")


def extract_id(s):
    m = re.search(r"(\d{5,})", s.strip())
    return m.group(1) if m else s.strip()


def get_info(session, song_id):
    page = session.get(f"https://www.gequbao.net/music/{song_id}")
    title, author = str(song_id), "unknown"
    m = re.search(r'window\.appData\s*=\s*(\{.*?\});', page)
    if m:
        try:
            d = json.loads(m.group(1))
            title = html.unescape(d.get("mp3_title", title))
            author = html.unescape(d.get("mp3_author", author))
        except Exception:
            pass
    return title, author


def download_one(session, song_id, hd=False):
    title, artist = get_info(session, song_id)
    print(f"[*] {title} - {artist} (ID: {song_id})")

    endpoint = "down_mp3_hd" if hd else "down_mp3"
    url = f"https://www.gequbao.net/api/{endpoint}/{song_id}"
    print(f"[*] Requesting {endpoint}...")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": f"https://www.gequbao.net/music/{song_id}"})
        resp = session.opener.open(req, timeout=120)
        ct = resp.headers.get("Content-Type", "")
        cl = int(resp.headers.get("Content-Length", 0))

        if "audio" not in ct and cl < 100000:
            print(f"[-] Failed: {ct}, {cl} bytes")
            return False

        safe = re.sub(r'[\\/:*?"<>|]', "_", f"{artist} - {title}")
        ext = ".mp3"
        suffix = " (HQ)" if hd else ""
        outdir = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = os.path.join(outdir, safe + suffix + ext)

        if os.path.exists(filepath):
            print(f"[!] Already exists: {filepath}")
            return True

        print(f"[*] Downloading {cl} bytes...")
        downloaded = 0
        with open(filepath, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if cl > 0:
                    pct = downloaded * 100 / cl
                    bar = "=" * int(pct // 2) + ">" + " " * (50 - int(pct // 2))
                    print(f"\r    [{bar}] {pct:.1f}% ({downloaded}/{cl})", end="", flush=True)
                else:
                    print(f"\r    {downloaded} bytes", end="", flush=True)
        print()

        if downloaded < 10000:
            print(f"[!] Too small ({downloaded} bytes), removing")
            os.remove(filepath)
            return False

        print(f"[+] Saved: {filepath}")
        return True

    except Exception as e:
        print(f"[-] Error: {e}")
        return False


def search(session, keyword):
    print(f"[*] Searching: {keyword}")
    page = session.get(f"https://www.gequbao.net/s/{urllib.parse.quote(keyword)}")

    results = []
    seen = set()
    for m in re.finditer(
        r'href="/search_music\?song_id=(\d+)&kwd=[^"]*?&title=([^&"]*)&singer=([^&"]*)',
        page,
    ):
        kuwo_id = m.group(1)
        if kuwo_id in seen:
            continue
        seen.add(kuwo_id)
        title = html.unescape(urllib.parse.unquote_plus(m.group(2)))
        singer = html.unescape(urllib.parse.unquote_plus(m.group(3)))
        results.append({"kuwo_id": kuwo_id, "title": title, "singer": singer})

    if not results:
        print("[-] No results")
        return []

    print(f"[+] Found {len(results)} songs:")
    for i, s in enumerate(results):
        print(f"    {i+1}. {s['title']} - {s['singer']}")

    return results


def resolve_and_download(session, result, hd=False):
    title = result["title"]
    singer = result["singer"]
    kuwo_id = result["kuwo_id"]
    print(f"\n[*] Resolving: {title} - {singer}")

    search_url = (
        f"https://www.gequbao.net/search_music?"
        f"song_id={kuwo_id}&kwd={urllib.parse.quote(title)}"
        f"&title={urllib.parse.quote(title)}&singer={urllib.parse.quote(singer)}&page=1"
    )
    page = session.get(search_url)

    m = re.search(r'window\.appData\s*=\s*(\{.*?\});', page)
    if not m:
        print("[-] Could not find song data")
        return False

    try:
        data = json.loads(m.group(1))
        mp3_id = data.get("mp3_id")
        mp3_title = html.unescape(data.get("mp3_title", title))
        mp3_author = html.unescape(data.get("mp3_author", singer))
    except Exception:
        print("[-] Failed to parse song data")
        return False

    if not mp3_id:
        print("[-] No mp3_id found")
        return False

    print(f"[*] Found gequbao ID: {mp3_id} ({mp3_title} - {mp3_author})")
    return download_one(session, str(mp3_id), hd=hd)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    session = Session()
    arg = " ".join(sys.argv[1:])

    hd = "--hd" in arg
    arg = arg.replace("--hd", "").strip()

    if arg.lower().startswith("search"):
        keyword = arg[6:].strip()
        if not keyword:
            print("Usage: python gequbao_downloader.py search <keyword>")
            return
        results = search(session, keyword)
        if not results:
            return

        if len(results) == 1:
            resolve_and_download(session, results[0], hd=hd)
        else:
            choice = input(f"\nSelect (1-{len(results)}): ").strip()
            try:
                idx = int(choice) - 1
                resolve_and_download(session, results[idx], hd=hd)
            except (ValueError, IndexError):
                print("[-] Invalid")

    elif arg.lower().startswith("batch"):
        ids = arg[5:].strip().split(",")
        for sid in ids:
            sid = sid.strip()
            if sid:
                download_one(session, sid, hd=hd)
                time.sleep(0.5)

    else:
        song_id = extract_id(arg)
        download_one(session, song_id, hd=hd)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[-] Cancelled")
