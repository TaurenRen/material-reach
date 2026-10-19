"""cli — material-reach 命令行入口。

用法：
  mr doctor                      素材链路体检（ffmpeg/yt-dlp/bili-cli/node/JS runtime）
  mr grab <url> --out 素材库/    按渠道路由抓取落盘（YouTube视频+B站元数据+网页封面）
  mr douyin <url...> --out 素材库/  抖音采集（长/短链/主页/搜索页，游客态）
  mr codec-fix 目录 [--check]    批量 AV1/VP9 → H.264 兼容性转码
  mr index 目录                  盘点素材库，产出 INDEX.jsonl / INDEX.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .doctor import run_doctor


def cmd_grab(args) -> int:
    from .grab import grab, route_url
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ch = route_url(args.url)
    print(f"[material-reach] 渠道: {ch} -> 落盘目录: {out}")
    r = grab(args.url, out)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    if r.get("ok"):
        e = r["entry"]
        print(f"✅ 已落盘: {e.get('file') or e.get('cover')}")
        if e.get("note"):
            print(f"   ⚠ {e['note']}")
        return 0
    print(f"❌ 抓取失败: {r.get('error', '未知错误')}")
    return 1


def cmd_douyin(args) -> int:
    from .douyin import grab_douyin
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(f"[material-reach] 抖音采集 -> {out}")
    rs = grab_douyin(args.urls, out, max_n=args.max, visible=args.visible)
    if args.json:
        print(json.dumps(rs, ensure_ascii=False, indent=2))
    ok = sum(1 for r in rs if r.get("ok"))
    for r in rs:
        if r.get("ok"):
            print(f"  ✅ {r['id']} {r.get('size', 0)/1048576:.1f}MB {r.get('title','')[:36]}")
        else:
            print(f"  ❌ {r.get('id', '?')} {r.get('error', '')}")
    print(f"[material-reach] 完成 {ok}/{len(rs)}")
    return 0 if ok else 1


def cmd_codecfix(args) -> int:
    from .codecfix import main as cf
    argv = [args.dir] + (["--check"] if args.check else [])
    return cf(argv)


def cmd_index(args) -> int:
    from .indexer import main as ix
    return ix([args.dir])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="mr",
        description="material-reach — 短视频素材搜集能力层（grab / codec-fix / index / doctor）")
    ap.add_argument("--version", action="version", version=f"material-reach {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("doctor", help="素材链路体检，处方式修复提示")
    p1.add_argument("--json", action="store_true", help="JSON 输出")
    p1.set_defaults(fn=lambda a: (run_doctor(as_json=a.json), 0)[1])

    p2 = sub.add_parser("grab", help="按 URL 渠道抓取素材，真正落盘")
    p2.add_argument("url", help="YouTube / B站 / 普通网页 URL")
    p2.add_argument("--out", default="素材库", help="落盘根目录（默认 ./素材库）")
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(fn=cmd_grab)

    p3 = sub.add_parser("douyin", help="抖音采集：长/短链、博主主页、搜索页（游客态）")
    p3.add_argument("urls", nargs="+", help="抖音 URL，可多个")
    p3.add_argument("--out", default="素材库", help="落盘根目录（默认 ./素材库）")
    p3.add_argument("--max", type=int, default=20, help="主页/搜索页最多采集条数")
    p3.add_argument("--visible", action="store_true", help="浏览器窗口可见（默认屏幕外）")
    p3.add_argument("--json", action="store_true")
    p3.set_defaults(fn=cmd_douyin)

    p4 = sub.add_parser("codec-fix", help="批量 AV1/VP9 → H.264")
    p4.add_argument("dir", help="素材目录")
    p4.add_argument("--check", action="store_true", help="只列出待修复，不转码")
    p4.set_defaults(fn=cmd_codecfix)

    p5 = sub.add_parser("index", help="盘点素材库，产出 INDEX.jsonl / INDEX.md")
    p5.add_argument("dir", help="素材库根目录")
    p5.set_defaults(fn=cmd_index)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("\n中断"); return 130


if __name__ == "__main__":
    sys.exit(main())
