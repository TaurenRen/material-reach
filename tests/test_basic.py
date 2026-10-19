# -*- coding: utf-8 -*-
"""material-reach 基础单测：URL 路由 / 索引写入（纯函数，不依赖网络与 ffmpeg）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from material_reach.grab import route_url  # noqa: E402


def test_route_youtube():
    assert route_url("https://www.youtube.com/watch?v=y8NtMZ7VGmU") == "youtube"
    assert route_url("https://youtu.be/y8NtMZ7VGmU") == "youtube"


def test_route_bilibili():
    assert route_url("https://www.bilibili.com/video/BV1dYEc65EVE") == "bilibili"
    assert route_url("BV1dYEc65EVE") == "bilibili"


def test_route_web():
    assert route_url("https://mp.weixin.qq.com/s/abc") == "web"
    assert route_url("https://www.ted.com/talks/x") == "web"


def test_index_jsonl(tmp_path):
    from material_reach.grab import append_index
    append_index(tmp_path, {"id": "test", "source": "web", "url": "https://x"})
    line = (tmp_path / "INDEX.jsonl").read_text(encoding="utf-8").strip()
    data = json.loads(line)
    assert data["id"] == "test"
    assert "grabbed_at" in data


# ── douyin（纯函数，不依赖网络/浏览器） ─────────────────────────────────────
from material_reach.douyin import LONG_RE, pick_video_urls, resolve_share, safe_name  # noqa: E402


def test_douyin_resolve_long_url():
    assert resolve_share("https://www.douyin.com/video/7697283722604776745") == "7697283722604776745"


def test_douyin_safe_name():
    n = safe_name('危险/字符:*?"<>|\n标题', "123")
    assert "/" not in n and "\\" not in n and n.endswith("_123.mp4")
    assert safe_name("", "456") == "douyin_456.mp4"


def test_douyin_pick_urls():
    d = {"video": {"play_addr_265": {"url_list": ["https://a"]},
                   "play_addr_h264": {"url_list": ["https://b"]}}}
    assert pick_video_urls(d) == ["https://b"]          # h264 优先
    d2 = {"video": {"bit_rate": [{"play_addr": {"url_list": ["https://c"]}}]}}
    assert pick_video_urls(d2) == ["https://c"]         # bit_rate 兜底
    assert pick_video_urls({"video": {}}) == []


def test_douyin_share_re():
    assert LONG_RE.search("https://www.douyin.com/video/7367347842864482642?x=1").group(1) == "7367347842864482642"
