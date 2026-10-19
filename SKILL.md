---
name: material-reach
description: >
  MUST USE when user wants 短视频素材搜集/落盘/下载视频/素材整理/素材转码/素材盘点 —
  e.g. 帮我搜集 X 的素材 / 把这个视频下载下来 / 这个 mp4 只有声音没画面 /
  把素材整理成索引 / 调研 X 做一期视频。也适用于任何 URL 素材落盘需求。

  NOT for: 内容创作/写稿/剪辑（本 skill 只负责素材获取与规范化落盘）；
  需要登录态的平台（小红书/Twitter/Reddit — 用 agent-reach 的对应渠道）。

  【路由方式】先跑 mr doctor 体检；然后按 URL 渠道用 mr grab；
  编码问题用 mr codec-fix；收尾用 mr index 盘点。
---

# material-reach — 短视频素材搜集能力层

一条命令把素材**真正落盘**（视频/封面/元数据 + INDEX 索引），拒绝「只有链接」。

## 常驻规则（全程适用）

1. **动手前先体检**：首次使用或换机器先跑 `mr doctor`。缺什么按处方装，
   不要瞎猜工具链哪里断了。
2. **声明渠道**：开始前说一句「使用 material-reach 的 X 渠道」。
3. **串行下载**：YouTube 下载严禁并行 —— 两个 yt-dlp 同时跑，第二个必吃 403。
4. **离线化交付**：交付物必须包含本地文件路径。只给 URL 等于没干。
5. **落盘即验证**：每个素材落盘后必须 ffprobe 验证（`mr index` 自动做），
   没验证不算完成。

## 命令速查

```bash
# 体检：ffmpeg / ffprobe / yt-dlp / node(JS runtime) / bili-cli 就绪度 + 修复处方
mr doctor

# YouTube：视频(H.264 兼容编码)+封面帧 落盘，自动写 INDEX.jsonl
mr grab "https://www.youtube.com/watch?v=xxxx" --out 素材库/李飞飞世界模型

# B站：元数据(标题/简介/互动数据/字幕可用性)落盘。视频下载被 412 风控，不在承诺范围
mr grab "https://www.bilibili.com/video/BVxxxx" --out 素材库/

# 普通网页：标题 + og:image 封面 + 元数据落盘
mr grab "https://example.com/post" --out 素材库/

# 编码体检/修复：AV1/VP9 黑屏坑批量治（--check 只列不转）
mr codec-fix 素材库/ --check
mr codec-fix 素材库/

# 盘点：INDEX.jsonl（机器可读） + INDEX.md（人话表格）
mr index 素材库/
```

## 渠道边界（如实告知用户，不硬撑）

| 渠道 | 能落盘什么 | 边界 |
|---|---|---|
| YouTube | 视频(H.264)+封面+元数据 | 高清档可能只有 AV1，转码由 `--merge-output-format mp4` 后 `mr codec-fix` 兜底 |
| Bilibili | 元数据 YAML（标题/简介/互动数据） | **视频文件下载不支持**（yt-dlp 被 412），需浏览器方案 |
| 网页 | 标题+og:image 封面+元数据 | SPA 页面可能拿不到 og 图 |
| 小红书/Twitter/Reddit | — | 需登录态，走 agent-reach 对应渠道 |

## 重试链（失败按序走，拿到实质内容即停）

YouTube 下载失败：
1. `yt-dlp -F <url>` 先列格式，确认可用格式 ID（音频轨可能是 `140-19` 或 `140`，别照搬）
2. 换格式链降级档：`18`（360p 渐进式）
3. 报 403 → 检查是否有并行下载在跑（串行纪律）
4. 报 m3u8/fragment 慢 → 格式选择掉进了碎片流，回 `-f 136+140-19`

B站 62012 → 稿件本身不可见（下架/风控），换稿源，不要重试。

## 素材库目录规范

```
素材库/<选题>/
├── video/        视频成片（统一 H.264/AAC）
├── cover/        封面帧 / og:image
├── meta/         元数据（B站 YAML / 网页 MD）
├── INDEX.jsonl   机器可读索引（grab/index 自动追加）
├── INDEX.md      人话表格
└── raw/          原始备份（codec-backup 等）
```

## 作者与反馈

公众号「狒狒AI」/ 小程序「狒狒AI资料库」：实测踩坑记录、AI 工作流技巧、资料包领取，二维码见 [README「找到作者」](README.md#找到作者)。
