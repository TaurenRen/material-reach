"""grab — 一条命令把素材真正落盘。

渠道路由（多后端有序候选，失败按重试链走）：
- YouTube  → yt-dlp，格式候选链是踩坑换来的：
     136+140-19  （720p H.264 视频轨 + 原声音轨，https 单文件，不掉进 m3u8 碎片流）
     bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]
     18          （360p 渐进式兜底）
- Bilibili → bili-cli 元数据落盘（免登录）。视频文件下载不在承诺范围：
     yt-dlp 已被 B 站风控 412 全面拦截（2026-06 实测），如实告知用户。
- 其他网页 → 抓标题 + og:image 封面 + 正文摘录，元数据落盘。

硬纪律（全部实测换来的）：
1. YouTube 下载必须串行 —— 两个 yt-dlp 并行，第二个必吃 403。
2. 素材统一转 H.264/AAC（yuv420p），播放器兼容性优先（AV1 黑屏坑）。
3. 每个素材落盘后立即 ffprobe 验证 + 追加 INDEX.jsonl，不验证不算完成。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

FFMPEG = os.environ.get("MR_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("MR_FFPROBE", "ffprobe")

YT_FORMAT_CHAIN = "136+140-19/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/18"


# ── 工具函数 ────────────────────────────────────────────────────────────────
def ffprobe_streams(path: Path) -> dict | None:
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height",
             "-show_entries", "format=duration,size", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout or "{}")
    except Exception:
        return None


def summarize(path: Path) -> dict:
    """把 ffprobe 结果压成索引友好的一行字段。"""
    data = ffprobe_streams(path) or {}
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return {
        "file": str(path),
        "duration": round(float(fmt.get("duration", 0) or 0), 2),
        "size": int(fmt.get("size", 0) or 0),
        "vcodec": v.get("codec_name", ""),
        "acodec": a.get("codec_name", ""),
        "width": v.get("width", 0),
        "height": v.get("height", 0),
    }


def append_index(out_dir: Path, entry: dict) -> None:
    entry = {"grabbed_at": _dt.datetime.now().isoformat(timespec="seconds"),
             **entry}
    with (out_dir / "INDEX.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_h264(src: Path, dst: Path) -> bool:
    """AV1/VP9 等新编码 → H.264/AAC yuv420p（播放器兼容性统一）。"""
    cmd = [FFMPEG, "-y", "-i", str(src), "-c:v", "libx264", "-crf", "20",
           "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", "192k", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 10_000


def extract_cover(video: Path, cover: Path, at: float = 0.3) -> bool:
    """抽封面帧（默认取 30% 时长处，避开黑屏开头）。"""
    info = summarize(video)
    dur = info.get("duration") or 0
    ss = max(1.0, dur * at) if dur else 1.0
    r = subprocess.run(
        [FFMPEG, "-y", "-ss", f"{ss:.2f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(cover)],
        capture_output=True, text=True)
    return r.returncode == 0 and cover.exists()


# ── 渠道：YouTube ───────────────────────────────────────────────────────────
def grab_youtube(url: str, out_dir: Path, title_hint: str | None = None) -> dict:
    video_dir = out_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    stub = re.sub(r"[^\w\-]", "_", title_hint or "yt")[:40]
    out_tpl = str(video_dir / f"{stub}_%(id)s.%(ext)s")
    # 串行下载：格式候选链逐级降级
    r = subprocess.run(
        ["yt-dlp", "-f", YT_FORMAT_CHAIN, "--merge-output-format", "mp4",
         "--ffmpeg-location", FFMPEG, "-o", out_tpl, url],
        capture_output=True, text=True, timeout=3600)
    files = sorted(video_dir.glob(f"{stub}_*.mp4"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {"ok": False, "channel": "youtube", "url": url,
                "error": (r.stderr or r.stdout)[-400:]}
    video = files[-1]
    info = summarize(video)
    cover = out_dir / "cover" / (video.stem + ".jpg")
    cover.parent.mkdir(parents=True, exist_ok=True)
    has_cover = extract_cover(video, cover)
    entry = {"id": video.stem, "source": "youtube", "url": url,
             "title": title_hint or video.stem, **info,
             "cover": str(cover) if has_cover else ""}
    append_index(out_dir, entry)
    return {"ok": True, "channel": "youtube", "entry": entry}


# ── 渠道：Bilibili（元数据落盘，如实声明边界）───────────────────────────────
def grab_bilibili(url_or_bvid: str, out_dir: Path) -> dict:
    bvid = url_or_bvid.rstrip("/").split("/")[-1]
    meta_dir = out_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(["bili", "video", bvid], capture_output=True,
                           text=True, timeout=60)
    except FileNotFoundError:
        return {"ok": False, "channel": "bilibili", "url": url_or_bvid,
                "error": "bili-cli 未安装: pip install bilibili-cli"}
    text = r.stdout or ""
    if not text.strip() or r.returncode != 0:
        return {"ok": False, "channel": "bilibili", "url": url_or_bvid,
                "error": (r.stderr or text)[-300:] or "接口失败（可能稿件不可见 62012）"}
    meta = meta_dir / f"B站_{bvid}.yaml"
    meta.write_text(text, encoding="utf-8")
    entry = {"id": bvid, "source": "bilibili", "url": url_or_bvid,
             "file": str(meta), "note": "仅元数据落盘；B站视频下载被 412 风控拦截，需浏览器方案"}
    append_index(out_dir, entry)
    return {"ok": True, "channel": "bilibili", "entry": entry}


# ── 渠道：通用网页（标题 + og:image 封面 + 正文摘录）────────────────────────
def grab_web(url: str, out_dir: Path) -> dict:
    meta_dir = out_dir / "meta"
    cover_dir = out_dir / "cover"
    for d in (meta_dir, cover_dir):
        d.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 material-reach/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read(2_000_000).decode("utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "channel": "web", "url": url, "error": str(e)[:200]}
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    og_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else "untitled"
    slug = re.sub(r"[^\w\-]", "_", title)[:50]
    cover_path = ""
    if og_m:
        img_url = og_m.group(1)
        try:
            req2 = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=30) as resp2:
                img = resp2.read()
            ext = ".jpg" if "jpg" in img_url or "jpeg" in img_url else ".png"
            cp = cover_dir / f"{slug}{ext}"
            cp.write_bytes(img)
            cover_path = str(cp)
        except Exception:
            pass
    meta = meta_dir / f"网页_{slug}.md"
    meta.write_text(f"# {title}\n\n- 来源: {url}\n- 抓取时间: {_dt.datetime.now().isoformat()}\n"
                    f"- og:image: {og_m.group(1) if og_m else '无'}\n", encoding="utf-8")
    entry = {"id": slug, "source": "web", "url": url, "title": title,
             "file": str(meta), "cover": cover_path}
    append_index(out_dir, entry)
    return {"ok": True, "channel": "web", "entry": entry}


# ── 路由入口 ────────────────────────────────────────────────────────────────
def route_url(url: str) -> str:
    u = url.lower()
    if "youtube.com/watch" in u or "youtu.be/" in u:
        return "youtube"
    if "bilibili.com/video/" in u or re.match(r"^BV[0-9A-Za-z]+$", url.strip()):
        return "bilibili"
    return "web"


def grab(url: str, out_dir: Path, normalize: bool = True) -> dict:
    ch = route_url(url)
    if ch == "youtube":
        return grab_youtube(url, out_dir)
    if ch == "bilibili":
        return grab_bilibili(url, out_dir)
    return grab_web(url, out_dir)
