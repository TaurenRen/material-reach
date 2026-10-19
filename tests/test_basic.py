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
