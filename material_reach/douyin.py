"""douyin — 抖音网页版视频采集（游客态，无需登录）。

原理（2026-10-19 实测）：
  1. douyin.com 游客态可直接打开，推荐流/搜索页 HTML 里就带 /video/<id> 链接；
  2. 页面上下文里 fetch `/aweme/v1/web/aweme/detail?aweme_id=<id>&aid=6383&version_code=190500`
     （credentials:'include' 带游客 cookie）返回完整 aweme_detail，
     video.play_addr(_h264/_265).url_list 就是视频直链（douyinvod CDN）；
  3. douyinvod 校验 Referer —— 下载时带 `Referer: https://www.douyin.com/` 即可，
     无需登录、无需签名（ aid=6383 是 web 端固定 aid ）。
  headless 会被风控弹验证码，必须用有头窗口（可用屏幕外坐标不打扰操作者）。

本模块为独立实现，不依赖任何浏览器插件。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DETAIL_API = ("/aweme/v1/web/aweme/detail?aid=6383&version_code=190500&aweme_id=")
VIDEO_ID_RE = re.compile(r"/video/(\d{15,21})")
SHARE_RE = re.compile(r"(?:https?://)?v\.douyin\.com/[A-Za-z0-9]+")
LONG_RE = re.compile(r"(?:https?://)?www\.douyin\.com/video/(\d{15,21})")


def _find_chrome() -> str:
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(p).exists():
            return p
    raise RuntimeError("未找到 chrome.exe")


def _find_driver() -> str:
    base = Path.home() / r".cache\selenium\chromedriver\win64"
    cands = []
    for p in base.glob("*/chromedriver.exe"):
        try:
            cands.append((tuple(int(x) for x in re.findall(r"\d+", p.parent.name)), str(p)))
        except ValueError:
            continue
    cands.sort(reverse=True)
    if not cands:
        raise RuntimeError("未找到 chromedriver（.cache\\selenium\\chromedriver\\win64）")
    return cands[0][1]


def resolve_share(url: str) -> str:
    """v.douyin.com 短链 -> 19 位视频 ID；长链直接提取；其余原样返回。"""
    m = LONG_RE.search(url)
    if m:
        return m.group(1)
    if SHARE_RE.search(url):
        import requests
        r = requests.get(SHARE_RE.search(url).group(0), allow_redirects=True,
                         headers={"User-Agent": UA}, timeout=30)
        m = LONG_RE.search(r.url) or VIDEO_ID_RE.search(r.text)
        if m:
            return m.group(1)
    m = VIDEO_ID_RE.search(url)
    return m.group(1) if m else ""


class DouyinBrowser:
    """有头（屏幕外）Chrome —— 抖音对 headless 弹验证码，别用 headless。"""

    def __init__(self, profile: str | Path | None = None, visible: bool = False):
        os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        o = Options()
        o.binary_location = _find_chrome()
        prof = Path(profile or Path.home() / ".material-reach" / "douyin-profile")
        prof.mkdir(parents=True, exist_ok=True)
        o.add_argument(f"--user-data-dir={prof}")
        o.add_argument("--no-sandbox")
        o.add_argument("--no-first-run")
        o.add_argument("--no-default-browser-check")
        o.add_argument("--disable-features=ProfilePicker,Translate,CalculateNativeWinOcclusion")
        o.add_argument("--disable-backgrounding-occluded-windows")
        if visible:
            o.add_argument("--window-size=1400,900")
        else:
            o.add_argument("--window-size=1400,900")
            o.add_argument("--window-position=-2400,-800")  # 屏幕外，不打扰操作者
        self._drv = None
        last = None
        for cand in [Path(_find_driver())]:
            try:
                self._drv = webdriver.Chrome(service=Service(str(cand)), options=o)
                break
            except Exception as e:  # 驱动版本不匹配逐个兜底
                last = e
        if self._drv is None:
            # 全目录候选
            base = Path.home() / r".cache\selenium\chromedriver\win64"
            for cand in sorted(base.glob("*/chromedriver.exe"), reverse=True):
                try:
                    self._drv = webdriver.Chrome(service=Service(str(cand)), options=o)
                    break
                except Exception as e:
                    last = e
        if self._drv is None:
            raise RuntimeError(f"chromedriver 均不可用: {last}")

    def open_site(self) -> None:
        self._drv.get("https://www.douyin.com/")
        for _ in range(8):
            time.sleep(2)
            if "验证" not in (self._drv.title or ""):
                break
        if "验证" in (self._drv.title or ""):
            raise RuntimeError("抖音风控验证码页：请稍后重试或用 visible=True 人工过一次验证")

    def fetch_detail(self, aweme_id: str) -> dict | None:
        """页面上下文带 cookie 调 detail 接口（与浏览器登录态无关，游客可用）。"""
        self._drv.set_script_timeout(30)
        raw = self._drv.execute_async_script(
            "var v=arguments[0],cb=arguments[arguments.length-1];"
            "fetch('" + DETAIL_API + "' + v, {credentials:'include'})"
            ".then(function(r){return r.text();})"
            ".then(function(t){cb(t.slice(0,500000));})"
            ".catch(function(e){cb(JSON.stringify({err:String(e)}));});",
            aweme_id)
        if not raw:
            return None
        d = json.loads(raw)
        if d.get("err"):
            raise RuntimeError(f"detail 接口失败: {d['err']}")
        return d.get("aweme_detail") or None

    def collect_ids(self, page_url: str, max_n: int = 20, scrolls: int = 15) -> list[str]:
        """打开某个页面（博主主页/搜索页/推荐流），滚动收集视频 ID。"""
        self._drv.get(page_url)
        time.sleep(5)
        ids: list[str] = []
        for _ in range(scrolls):
            html = self._drv.page_source or ""
            ids = list(dict.fromkeys(VIDEO_ID_RE.findall(html)))
            if len(ids) >= max_n:
                break
            try:
                self._drv.execute_script("window.scrollBy(0, 2400);")
            except Exception:
                pass
            time.sleep(1.5)
        return ids[:max_n]

    def quit(self) -> None:
        try:
            self._drv.quit()
        except Exception:
            pass


def pick_video_urls(detail: dict) -> list[str]:
    """aweme_detail.video 里按 h264 > 265 > play_addr 取直链（含清晰度档位兜底）。"""
    v = detail.get("video") or {}
    ordered = [v.get("play_addr_h264"), v.get("play_addr_265"), v.get("play_addr")]
    for pa in ordered:
        if pa and pa.get("url_list"):
            return list(pa["url_list"])
    # 兜底：bit_rate 档位
    for br in v.get("bit_rate") or []:
        if br.get("play_addr", {}).get("url_list"):
            return list(br["play_addr"]["url_list"])
    return []


def download(url: str, out: Path, referer: str = "https://www.douyin.com/") -> Path:
    """douyinvod 校验 Referer；分片下载带重试（防断流报废）。"""
    import requests
    headers = {"User-Agent": UA, "Referer": referer}
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        h = requests.head(url, headers=headers, timeout=30, allow_redirects=True)
        total = int(h.headers.get("Content-Length", 0))
    except Exception:
        pass
    if total <= 0:
        with requests.get(url, headers=headers, timeout=60, stream=True) as r:
            r.raise_for_status()
            with out.open("wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
    else:
        chunk_size, pos = 2 << 20, 0
        with out.open("wb") as f:
            while pos < total:
                end = min(pos + chunk_size - 1, total - 1)
                data = bytearray()
                for _ in range(5):
                    try:
                        rr = requests.get(url, headers={**headers,
                                          "Range": f"bytes={pos}-{end}"},
                                          timeout=60, stream=True)
                        rr.raise_for_status()
                        data = bytearray()
                        for chunk in rr.iter_content(1 << 16):
                            data.extend(chunk)
                        if len(data) == end - pos + 1:
                            break
                    except Exception:
                        data = bytearray()
                        time.sleep(2)
                if len(data) != end - pos + 1:
                    raise RuntimeError(f"分片下载失败 {pos}-{end}/{total}")
                f.write(data)
                pos = end + 1
    if out.stat().st_size < 4096:
        raise RuntimeError("文件过小，直链可能失效")
    return out


def safe_name(s: str, aweme_id: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\r\n#]+", "_", (s or "").strip())[:60]
    return f"{s}_{aweme_id}.mp4" if s else f"douyin_{aweme_id}.mp4"


def grab_douyin(urls: list[str], out_dir: Path, max_n: int = 20,
                visible: bool = False, browser: DouyinBrowser | None = None
                ) -> list[dict]:
    """入口：任意数量的抖音链接（长/短链/主页/搜索页），落盘 mp4。"""
    import requests  # noqa: F401  提前失败
    own = browser is None
    br = browser or DouyinBrowser(visible=visible)
    results: list[dict] = []
    try:
        # 归一化：把输入拆成 aweme_id / 需要开页面收集的入口
        ids: list[str] = []
        entries: list[str] = []
        for u in urls:
            vid = resolve_share(u)
            if vid:
                ids.append(vid)
            elif "douyin.com" in u:
                entries.append(u if u.startswith("http") else "https://" + u)
        if entries:
            br.open_site()
            for e in entries:
                for vid in br.collect_ids(e, max_n=max_n):
                    ids.append(vid)
        ids = list(dict.fromkeys(ids))
        if not ids:
            return [{"ok": False, "error": "未解析出任何视频 ID", "input": urls}]
        # 必须先落到 douyin.com 域，页面上下文里的相对路径 fetch 才有效
        try:
            cur = br._drv.current_url or ""
        except Exception:
            cur = ""
        if "douyin.com" not in cur:
            br.open_site()
        for vid in ids:
            try:
                detail = br.fetch_detail(vid)
                if detail is None:
                    results.append({"ok": False, "id": vid,
                                    "error": "aweme_detail 为空（可能私密/已删/风控）"})
                    continue
                results.append(_download_one(br, vid, detail, out_dir))
            except Exception as e:
                results.append({"ok": False, "id": vid, "error": str(e)[:160]})
    finally:
        if own:
            br.quit()
    return results


def _download_one(br: DouyinBrowser, vid: str, detail: dict, out_dir: Path) -> dict:
    urls = pick_video_urls(detail)
    if not urls:
        return {"ok": False, "id": vid, "error": "无直链（直播/图文/私密？）"}
    name = safe_name(detail.get("desc") or detail.get("caption"), vid)
    path = download(urls[0], out_dir / name)
    author = (detail.get("author") or {}).get("nickname", "")
    return {"ok": True, "id": vid, "file": str(path),
            "title": (detail.get("desc") or "")[:50],
            "author": author,
            "size": path.stat().st_size,
            "duration": (detail.get("video") or {}).get("duration")}
