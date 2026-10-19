"""doctor — 素材链路体检。

学 Agent Reach 的 probe 思想：真执行上游命令拿版本号，不做 which() 纸面检查；
每个探测失败都给出可复制的修复处方。输出人话表格 + --json。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 体检项：key / 人话名 / 探测命令 / 失败处方
CHECKS = [
    ("ffmpeg", "ffmpeg 编解码（合轨/转码/抽帧必需）",
     ["ffmpeg", "-version"], None),
    ("ffprobe", "ffprobe 流探测（索引/编码检测必需）",
     ["ffprobe", "-version"], None),
    ("yt-dlp", "yt-dlp（YouTube 下载/字幕）",
     ["yt-dlp", "--version"],
     "pip install -U yt-dlp   # 或装进你的 venv"),
    ("node", "Node.js（yt-dlp 的 JS runtime，过 YouTube 机检）",
     ["node", "--version"],
     "安装 Node.js LTS：https://nodejs.org"),
    ("bili", "bili-cli（B 站搜索/详情，免登录）",
     ["bili", "--version"],
     "pip install bilibili-cli"),
]


def _probe(name: str, desc: str, cmd: list[str], fix: str | None) -> dict:
    exe = shutil.which(cmd[0])
    if not exe:
        return {"key": name, "ok": False, "status": "missing",
                "desc": desc, "detail": f"未找到 {cmd[0]}",
                "fix": fix or f"安装 {cmd[0]}"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        line = (r.stdout or r.stderr).strip().splitlines()
        ver = line[0][:80] if line else ""
        return {"key": name, "ok": True, "status": "ok",
                "desc": desc, "detail": ver, "fix": None}
    except Exception as e:  # 装了但坏（如 venv shebang 失效）
        return {"key": name, "ok": False, "status": "broken",
                "desc": desc, "detail": str(e)[:120],
                "fix": f"重装 {cmd[0]}（当前可执行文件损坏）"}


def check_ytdlp_js_runtime() -> dict:
    """yt-dlp 新版需要 JS runtime 过 YouTube 机检。
    Windows 配置在 ~/.config/yt-dlp/config；没有就给处方。"""
    cfg = Path.home() / ".config" / "yt-dlp" / "config"
    ytdlp = next((c for c in CHECKS if c[0] == "yt-dlp"), None)
    if ytdlp is None or not _probe(*ytdlp)["ok"]:
        return {"key": "yt-dlp-js", "ok": False, "status": "skipped",
                "desc": "yt-dlp JS runtime 配置", "detail": "yt-dlp 本体未就绪",
                "fix": None}
    if cfg.exists() and "--js-runtimes" in cfg.read_text(encoding="utf-8", errors="ignore"):
        return {"key": "yt-dlp-js", "ok": True, "status": "ok",
                "desc": "yt-dlp JS runtime 配置", "detail": str(cfg), "fix": None}
    return {"key": "yt-dlp-js", "ok": False, "status": "needs-config",
            "desc": "yt-dlp JS runtime 配置",
            "detail": f"{cfg} 缺 --js-runtimes",
            "fix": "PowerShell 执行: Add-Content -Path $env:USERPROFILE\\.config\\yt-dlp\\config -Value '--js-runtimes node'"}


def run_doctor(as_json: bool = False) -> dict:
    results = [_probe(*c) for c in CHECKS] + [check_ytdlp_js_runtime()]
    ok_n = sum(1 for r in results if r["ok"])
    report = {"ok": ok_n, "total": len(results), "items": results}
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    print("material-reach doctor — 素材链路体检")
    print("=" * 56)
    print("图例: ✅ 可用  [!] 需配置  [X] 未安装/损坏\n")
    for r in results:
        mark = "✅" if r["ok"] else ("[!]" if r["status"] in ("needs-config",) else "[X]")
        print(f" {mark} {r['desc']}")
        print(f"      {r['detail']}")
        if r.get("fix"):
            print(f"      修复: {r['fix']}")
    print(f"\n状态: {ok_n}/{len(results)} 项就绪"
          + ("" if ok_n == len(results) else " —— 按上面处方补齐后重跑 mr doctor"))
    return report
