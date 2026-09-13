#!/usr/bin/env python3
"""
歌曲宝 (gequbao.net) 音乐下载器
用法:
  python gequbao_downloader.py <歌曲ID或URL>
  python gequbao_downloader.py search <关键词>
  python gequbao_downloader.py batch <ID1,ID2,...>
示例:
  python gequbao_downloader.py 3322385
  python gequbao_downloader.py https://www.gequbao.net/music/3322385
  python gequbao_downloader.py search Vertigo
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
        return self.opener.open(req, timeout=15).read().decode("utf-8", errors="ignore")

    def post_json(self, url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": UA,
                "Content-Type": "application/json",
                "Referer": "https://www.gequbao.net/",
            },
            method="POST",
        )
        return json.loads(self.opener.open(req, timeout=15).read().decode())

    def download(self, url, filepath):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.gequbao.net/"})
        resp = self.opener.open(req, timeout=120)
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(filepath, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 / total
                    bar = "=" * int(pct // 2) + ">" + " " * (50 - int(pct // 2))
                    print(f"\r    [{bar}] {pct:.1f}% ({downloaded}/{total})", end="", flush=True)
                else:
                    print(f"\r    {downloaded} bytes", end="", flush=True)
        print()
        return downloaded


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
            print(f"[-] Got non-audio response: {ct}, {cl} bytes")
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
            print(f"[!] Warning: file too small ({downloaded} bytes), may be incomplete")
            os.remove(filepath)
            return False

        print(f"[+] Saved: {filepath}")
        return True

    except Exception as e:
        print(f"[-] Error: {e}")
        return False


def search(session, keyword):
    print(f"[*] Searching: {keyword}")
    result = session.post_json("https://www.gequbao.net/api/search", {"keyword": keyword, "page": 1})
    songs = result.get("data", {}).get("list", [])
    if not songs:
        print("[-] No results")
        return []
    print(f"[+] Found {len(songs)} songs:")
    for i, s in enumerate(songs):
        print(f"    {i+1}. {html.unescape(s.get('name', '?'))} - {html.unescape(s.get('author', '?'))}  (ID: {s.get('id', '')})")
    return songs


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
        songs = search(session, keyword)
        if not songs:
            return
        choice = input(f"\nSelect (1-{len(songs)}): ").strip()
        try:
            song_id = songs[int(choice) - 1]["id"]
        except (ValueError, IndexError):
            print("[-] Invalid")
            return
        download_one(session, song_id, hd=hd)

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
