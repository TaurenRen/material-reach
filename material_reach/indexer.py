"""indexer — 素材库盘点：遍历目录，ffprobe 每个视频，产出 INDEX.jsonl + INDEX.md。"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .grab import summarize

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".flv"}


def build_index(root: Path) -> list[dict]:
    rows = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in VIDEO_EXTS or not p.is_file():
            continue
        if "codec-backup" in str(p) or ".bak" in p.name:
            continue
        info = summarize(p)
        rel = p.relative_to(root)
        rows.append({"file": str(rel).replace("\\", "/"), **info})
    return rows


def write_index(root: Path) -> tuple[Path, Path]:
    rows = build_index(root)
    jl = root / "INDEX.jsonl"
    with jl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    md = root / "INDEX.md"
    total_mb = sum(r.get("size", 0) for r in rows) / 1024 / 1024
    lines = [
        f"# 素材库索引：{root.name}",
        "",
        f"> 生成时间 {_dt.datetime.now().isoformat(timespec='seconds')} · "
        f"{len(rows)} 个媒体文件 · {total_mb:.1f} MB",
        "",
        "| 文件 | 时长(s) | 编码 | 分辨率 | 大小(MB) |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['file']} | {r.get('duration', 0)} | "
            f"{r.get('vcodec', '?')}/{r.get('acodec', '?')} | "
            f"{r.get('width', 0)}x{r.get('height', 0)} | "
            f"{r.get('size', 0) / 1024 / 1024:.1f} |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jl, md


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="素材库盘点，产出 INDEX.jsonl / INDEX.md")
    ap.add_argument("dir", help="素材库根目录")
    args = ap.parse_args(argv)
    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"目录不存在: {root}")
        return 1
    jl, md = write_index(root)
    rows = build_index(root)
    print(f"✅ {len(rows)} 个媒体文件 -> {jl}")
    print(f"   {md}")
    return 0
