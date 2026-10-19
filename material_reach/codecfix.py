"""codec-fix — 批量把 AV1/VP9 视频转成 H.264，治「只有声音没画面」。

背景（实测踩坑）：YouTube 高清档现在只发 AV1；Windows 自带播放器/部分剪辑软件
解码 AV1 会黑屏。ffprobe 检测 vcodec∈{av1, vp9} → 转码 libx264，原文件备份。
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .grab import FFMPEG, FFPROBE, normalize_h264, summarize

NEED_FIX = {"av1", "vp9"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}


def scan_dir(root: Path, check_only: bool = False, backup_dir: Path | None = None) -> list[dict]:
    results = []
    videos = [p for p in root.rglob("*")
              if p.suffix.lower() in VIDEO_EXTS and p.is_file()
              and ".bak" not in p.name]
    for v in videos:
        info = summarize(v)
        codec = (info.get("vcodec") or "").lower()
        if not codec:
            results.append({"file": str(v), "vcodec": "?", "status": "probe-failed"})
            continue
        if codec not in NEED_FIX:
            results.append({"file": str(v), "vcodec": codec, "status": "ok"})
            continue
        if check_only:
            results.append({"file": str(v), "vcodec": codec, "status": "needs-fix"})
            continue
        # 转码：原文件移入备份目录
        bdir = backup_dir or (root / "raw" / "codec-backup")
        bdir.mkdir(parents=True, exist_ok=True)
        bak = bdir / v.name
        n = 1
        while bak.exists():
            bak = bdir / f"{v.stem}_{n}{v.suffix}"
            n += 1
        shutil.move(str(v), str(bak))
        ok = normalize_h264(bak, v)
        results.append({"file": str(v), "vcodec": codec,
                        "status": "fixed" if ok else "fix-failed",
                        "backup": str(bak), **({} if ok else {"note": "转码失败，原文件在备份目录"})})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量 AV1/VP9 → H.264 兼容性转码")
    ap.add_argument("dir", help="要扫描的素材目录")
    ap.add_argument("--check", action="store_true", help="只体检列出，不转码")
    args = ap.parse_args(argv)
    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"目录不存在: {root}")
        return 1
    rows = scan_dir(root, check_only=args.check)
    fixed = sum(1 for r in rows if r["status"] == "fixed")
    need = sum(1 for r in rows if r["status"] == "needs-fix")
    for r in rows:
        icon = {"ok": "✅", "needs-fix": "[!]", "fixed": "🔧",
                "fix-failed": "[X]", "probe-failed": "?"}.get(r["status"], " ")
        extra = f" -> 备份 {r['backup']}" if r.get("backup") else ""
        print(f" {icon} [{r['vcodec']:>5}] {r['file']}{extra}")
    print(f"\n共 {len(rows)} 个视频: {fixed} 已修复, {need} 待修复"
          + ("（--check 模式，未转码）" if args.check else ""))
    return 0
