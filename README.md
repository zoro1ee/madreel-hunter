# madreel-hunter

> 以 TMDB 媒体标识为输入，在 [MADREEL](https://madow.tv) 上匹配 115 分享、本地打分排序、解锁并投递到你的媒体库工作流——零第三方依赖的单文件式 Python 工具。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#安装)

---

## 这个工具解决什么问题

MADREEL 的 OpenAPI v2 刻意只做「查询与解锁」：

- `list-shares` **不接受关键词搜索**，只吃 `tmdb_id` / `media_type` / `resource_id`；
- 返回的是一堆候选分享，**选哪一个由调用方决定**；
- 每个分享带一条 pipe 分隔的 DT2 TAG（`DT2|4K|WEB-DL|NF|HEVC|10BIT|DV|DDP5.1|ATMOS|CHS|MKV`），需要自己解析出清晰度、片源、HDR、音轨、字幕。

于是每个接入方都要把同一套东西重写一遍：TMDB 搜索 → 查候选 → 解析 TAG → 打分 → 解锁 → 丢给下载器。

`madreel-hunter` 就是这部分，做成可直接命令行使用、也可当库调用的实现。

## 核心特性

| 能力 | 说明 |
|---|---|
| `mh doctor` 探针 | **不需要 SDK 就能判定 OpenAPI Key 真伪**：三阶段请求对比，看 key 停在校验链的哪一步 |
| DT2 TAG 解析 | 分辨率 / 片源 / 编码 / 位深 / HDR / 音轨 / 字幕 / 容器 / 平台，未知标签不丢弃 |
| 可解释打分 | 每一项加分都有 reason，权重可被 `config.toml` 覆盖，不做黑盒排序 |
| TMDB 集成 | 片名 → `tmdb_id` + `media_type`，补齐 OpenAPI 缺少的关键词搜索 |
| 硬过滤 | `--min-res` / `--chinese-sub` / `--share-kind`，先筛再排 |
| 交付 | 输出 JSON 到文件，或 POST webhook 给 MoviePilot / n8n / Home Assistant |
| 零依赖 | 只用标准库（`urllib` + `tomllib`），没有 `requests` / `httpx` 负担 |

## 为什么必须安装官方 SDK

OpenAPI v2 的每个业务请求都要套一层加密信封：

```json
{"codec":"dian115-openapi-v2","kid":"dys_xxxx","developer_application_id":123,
 "sdk_identity":"sealed-...","package_id":"dys_pkg_xxxx","package_fingerprint":"dys_fp_xxxx",
 "nonce":"...","ts":1730000000,"payload":"base64url(aes-gcm-json)","proof":"base64url(hmac-sha256)"}
```

密钥由 **OpenAPI Key + SDK token 共同派生**，`developer_application_id` / `sdk_identity` / `package_id` / `package_fingerprint` 是服务端密封身份，客户端无法伪造，服务端会逐项与数据库中的 SDK 记录比对。

所以本项目的定位很明确：

- **不需要 SDK 的部分**（doctor / TMDB / TAG / 打分 / 导出）全部可直接用；
- **业务调用**（`signin` / `list-shares` / `unlock` / `rss` / `share`）通过 `providers/sdk.py` 适配官方 `dian115_openapi` 包，未安装时给出明确指引而不是静默失败。

本项目**不会**尝试复刻加解密逻辑——那既做不到，也没有意义。

## 安装

```bash
git clone https://github.com/zoro1ee/madreel-hunter.git
cd madreel-hunter
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

要求 Python 3.11+（用到 `tomllib`）。运行时零第三方依赖；`pip install -e ".[dev]"` 会额外装 `pytest`。

## 快速开始

### 1. 先确认 Key 到底能不能用

```bash
export MADREEL_API_KEY=dys_xxxxxxxx...
mh doctor
```

真实输出：

```text
base_url        : https://madow.tv
endpoint alive  : yes (openapi_codec_required)
official SDK    : not installed
api key         : VALID  [openapi_codec_invalid] SDK identity invalid
control (bogus) : openapi_key_invalid
note            : Key passed the key check and stopped at the sealed SDK identity step — this is the expected result for a valid key without the official SDK.
note            : Official SDK not installed: business calls (signin/list-shares/unlock/rss) require an approved developer application.
```

原理：服务端是分阶段校验的，用一个必然被拒的假 key 做对照，就能知道真 key 停在哪一步。

| 请求 | 响应 | 结论 |
|---|---|---|
| 无 key，明文 body | `400 openapi_codec_required` | 端点存活，但还没开始校验 key |
| 假 key + 信封 | `401 openapi_key_invalid` | 对照组：key 阶段就被拒 |
| 真 key + 信封 | `401 openapi_codec_invalid (SDK identity invalid)` | **key 存在、未停用，只是缺 SDK** |

> 只发一次请求看到某个错误，什么都说明不了；必须有对照组。

### 2. 把片名换成 TMDB 标识

```bash
mh tmdb search "沙丘 2" --type movie --limit 3
```

### 3. 查候选、打分、解锁

```bash
mh hunt --query "沙丘2" --min-res 4K --chinese-sub --only-best --unlock --out out/dune2.json
```

未安装官方 SDK 时：

```text
OpenAPI v2 business calls need the official SDK (sealed identity + derived keys).
Run `mh doctor` to check your key, and apply for a developer application at https://madow.tv/openapiv2.
```

### 4. 单独玩 TAG

```bash
mh tag parse "DT2|4K|WEB-DL|NF|HEVC|10BIT|DV|DDP5.1|ATMOS|CHS|MUXED-SUB|MKV"
```

```text
resolution  : 4K
source      : WEB-DL
video_codec : HEVC
bit_depth   : 10BIT
hdr         : ['DV']
audio       : ['DDP5.1', 'ATMOS']
subtitles   : ['CHS', 'MUXED-SUB']
container   : MKV
platform    : NF
```

## 命令参考

```text
mh doctor                 探测端点 / key 有效性（支持 --json）
mh tmdb search <query>    TMDB 搜索，输出 tmdb_id + media_type
mh tag parse <tag>        解析 DT2 TAG
mh hunt                   查候选 → 打分 → 可选解锁 / 导出 / 推 webhook
mh config show            打印生效配置（key 只显示前 8 位 kid）
```

`mh hunt` 常用参数：

| 参数 | 作用 |
|---|---|
| `--query` / `--tmdb-id` | 二选一，前者自动过 TMDB |
| `--media-type` / `--season` | 门户侧媒体类型与季 |
| `--min-res` | `720P` / `1080P` / `4K` / `8K` |
| `--chinese-sub` | 只保留带中文字幕的分享 |
| `--only-best` | 只解锁排序第一 |
| `--unlock` | 真正调用 unlock 换取 115 链接 |
| `--out` | 候选列表写 JSON |
| `--webhook` / `--webhook-token` | 解锁结果推送到自定义地址 |

## 配置

```bash
cp config.example.toml config.toml   # 已在 .gitignore 中
```

优先级：`--config` 路径 → `./config.toml` → `~/.config/madreel-hunter/config.toml` → 环境变量（`MADREEL_API_KEY` / `MADREEL_BASE_URL` / `TMDB_API_KEY`）。

Key 永远不会出现在日志或 `mh config show` 的完整输出里，只显示 `kid`（前 8 位）。

## 打分策略

默认档位（可在 `[scoring]` 中覆盖任意一段）：

| 维度 | 示例权重 |
|---|---|
| 分辨率 | 8K 90 / 4K 80 / 1080P 60 / 720P 40 |
| 片源 | BLURAY-REMUX 40 / REMUX 38 / WEB-DL 30 / BLURAY 26 |
| HDR | DV 16 / HDR10+ 12 / HDR10 8 |
| 音轨 | ATMOS 10 / TRUEHD 8 / DTS-HD 6 |
| 中文字幕 | +10 |
| 热度 `use_count` | 上限 +20 |
| 离线分享 | -8 |

每一项命中都会写进 `reasons`，用 `--out` 导出后可直接复盘「为什么选了这条」。

```python
from madreel_hunter.scoring import rank

best = rank(shares, min_resolution="4K", require_chinese_sub=True)[:3]
for item in best:
    print(item.share.share_id, item.score, item.reasons)
```

## 架构

```text
cli.py
 ├── providers/probe.py   三阶段探针（无需 SDK）
 ├── providers/sdk.py     官方 SDK 适配（密封身份 + 加解密由 SDK 负责）
 ├── tmdb.py              片名 → tmdb_id
 ├── tag.py               DT2 TAG ↔ 结构化字段
 ├── scoring.py           可解释打分 / 硬过滤
 └── targets/             JSON 导出、webhook 推送
```

设计取向：**能做的一步做实，做不了的（加密业务调用）明确报错并指向官方 SDK**，不伪造、不静默降级。

## 开发

```bash
pip install -e ".[dev]"
pytest -q          # 13 passed
```

## 路线图

- [ ] `rss` 增量订阅常驻模式（游标持久化、5 分钟退避重试）
- [ ] `--json` 全命令结构化输出，便于被其他程序调用
- [ ] 可插拔打分器（按季 / 按剧集包大小）
- [ ] 直接对 MoviePilot 订阅 API 建媒体（当前通过 webhook）
- [ ] Docker 镜像

## 免责声明

本项目是 OpenAPI 客户端实现，只做**请求编排、元数据整理与本地排序**：

- 不抓取、不托管、不传播任何影视文件；
- 不提供在线播放或下载能力，解锁得到的 115 分享链接由用户自行处理；
- 影视元数据来自 TMDB，分享内容来自站点用户上传，版权归各自权利人；
- 请仅用于管理你已合法拥有的内容或个人学习交流，使用后果自负。

## License

[MIT](./LICENSE) © 2026 zoro1ee
