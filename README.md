# yt-auto：韭菜週報

每週美股週報頻道的製作中心：用搞笑卡通看完一週美股。沒有固定主持角色，**當週新聞裡的人物和公司就是這週的卡通角色**（Fed 主席、台積電董事長、哭哭的 AI 伺服器、生氣的加油機……）。

每週一支 5–6 分鐘的長片（大盤、本週大事、漲跌排行、「本週時事概念股」、下週行事曆），再從裡面剪 3 支 Shorts。圖表、卡通、字幕、縮圖、剪輯、上傳資料都由程式產生，你只要審稿和配音。

- 📈 經營策略、每週流程、紅線、收益路線圖：[`channel/strategy.md`](channel/strategy.md)
- 🎭 卡通角色庫：[`channel/cast.yaml`](channel/cast.yaml)（總表 [`channel/cast_sheet.png`](channel/cast_sheet.png)）
- 🖼 頻道頭像 [`channel/avatar.png`](channel/avatar.png)、橫幅 [`channel/banner.png`](channel/banner.png)
- 🎬 第一集（2026 第 42 週）：[`weeks/2026-w42/episode.yaml`](weeks/2026-w42/episode.yaml)

```
channel/          卡通角色庫、頭像、橫幅、頻道字型（fonts/：jf open 粉圓，SIL OFL 1.1）、經營策略
weeks/<週>/       episode.yaml（腳本）、market.json（行情）、voice/（你的錄音，不進 git）
yt_auto/          產線程式
build/            投影片、成片、Shorts、縮圖、上傳清單（不進 git）
reports/          每週頻道數據
```

## 安裝（第一次）

需要 Python 3.10 以上和 ffmpeg。

```bash
# Mac
brew install ffmpeg
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m yt_auto list
```

## 每週流程

```bash
python -m yt_auto new 2026-w43      # 1. 建新的一週（或直接請 Claude 寫好）
python -m yt_auto fetch 2026-w43    # 2. 抓本週行情 → weeks/2026-w43/market.json
#                                     3. 寫 / 審 weeks/2026-w43/episode.yaml
python -m yt_auto slides 2026-w43   # 4. 先看投影片和縮圖 → build/2026-w43/slides/
#                                     5. 錄音：weeks/2026-w43/voice/s01.m4a、s02.m4a…（每段一個檔）
python -m yt_auto build 2026-w43    # 6. 長片＋Shorts＋縮圖＋upload.md
#                                     7. 照 build/2026-w43/upload.md 在 YouTube Studio 上傳排程
```

**配音的優先順序**：`voice/` 裡有你的錄音就用錄音；沒有就用 edge-tts 產生預覽配音（需要網路）；都沒有就是靜音版，只用來看節奏（`build --no-tts`）。

**最省事的做法**：每週六直接跟 Claude 說「做這週的韭菜週報」。它會上網整理新聞、抓行情、寫好腳本並 commit，你只要審稿、錄音、`build`、上傳。

## 指令

| 指令 | 用途 |
|---|---|
| `python -m yt_auto list` | 每一週的發布時間、錄音進度、是否已剪好、是否已上傳 |
| `python -m yt_auto new 2026-w43` | 用範本建立新的一週 |
| `python -m yt_auto fetch [週]` | 用 Yahoo Finance 抓指數和觀察名單（名單在 `config.yaml`） |
| `python -m yt_auto validate [週]` | 檢查腳本：格式、長度、概念股有沒有標虛構、有沒有像在報明牌 |
| `python -m yt_auto slides [週]` | 只畫投影片和縮圖 |
| `python -m yt_auto build [週] [--no-tts] [--music 檔案]` | 剪出長片、Shorts、縮圖和上傳清單 |
| `python -m yt_auto upload [週] [--only long\|short1] [--dry-run]` | 用 YouTube API 上傳並排程（見下方限制） |
| `python -m yt_auto cast` | 把角色庫畫成總表，新增角色後確認造型 |
| `python -m yt_auto branding` | 重新產生頻道頭像、橫幅，和放到頻道頁的預覽圖 |
| `python -m yt_auto stats` | 產生頻道數據週報到 `reports/` |
| `python -m pytest` | 跑測試 |

省略「週」就是最新的一週。

## 腳本格式

每段一個 `segments` 項目，`type` 決定畫面：

| type | 畫面 | 需要的欄位 |
|---|---|---|
| `title` | 開場大標＋大數字 | `headline`、`stat`、`subhead` |
| `indices` | 指數週漲跌長條圖 | （讀 `market.json`） |
| `topic` | 一件大事：標題＋重點＋（選填）個股走勢圖 | `heading`、`bullets`、`chart` |
| `movers` | 觀察名單漲跌排行 | （讀 `market.json`） |
| `concept` | 本週時事概念股（虛構 K 線） | `name`、`change`、`series`、`labels` |
| `calendar` | 下週行事曆 | `events` |
| `outro` | 結尾 | `headline`、`bullets` |

每段都要有 `narration`（旁白，也是字幕）。`cast` 決定這段誰上台：

```yaml
cast:
  - {who: warsh, mood: zipped, say: 我不預判會議, quote: true}   # 真實人物的對話框只能放真實引述
  - {who: wei, mood: nervous, arms: hold, holding: {type: card, text: "EPS 4.60"}}
arrow: down   # 舞台背景的大趨勢線（up / down）
```

- `who`：`channel/cast.yaml` 裡的角色；本週新聞有新人物就先加進去。
- `mood`：`neutral`、`happy`、`laugh`、`shocked`、`nervous`、`cry`、`smug`、`angry`、`zipped`（嘴巴拉鍊）
- `arms`：`down`、`up`、`hold`、`shrug`、`facepalm`、`point`
- `holding`：手上拿 `card`（成績單）、`sign`（舉牌）、`cash`（鈔票）

有 `chapter` 的段落會自動變成 YouTube 章節。`shorts` 指定哪些段落要另外剪成直式 Short。

YAML 小提醒：文字裡有 ` #` 或 `: `（冒號加空白）時，整段要用雙引號包起來。

## 自動上傳（選用）

YouTube 有個限制：**用自己建立、還沒通過 YouTube 審核的 API 專案上傳，影片會被鎖在「私人」**。所以一開始照 `upload.md` 手動上傳最實際。想自動化的話：

1. [Google Cloud Console](https://console.cloud.google.com/) 建立專案，啟用 **YouTube Data API v3**。
2. 「OAuth 同意畫面」選外部，把自己的 Google 帳號加進測試使用者。
3. 「憑證」→ 建立 OAuth 用戶端 ID →「電腦版應用程式」，下載 JSON 存成 `.secrets/client_secret.json`。
4. `python -m yt_auto upload --dry-run` 確認內容，再拿掉 `--dry-run` 正式上傳。第一次會開瀏覽器登入。
5. 送出 [YouTube API 稽核表單](https://support.google.com/youtube/contact/yt_api_form)，通過後上傳的影片才能公開或排程。

## 頻道數據週報

`stats` 只讀公開資料，用 API 金鑰就好：Google Cloud 專案 →「憑證」→ 建立 API 金鑰，然後 `export YOUTUBE_API_KEY=你的金鑰`、`python -m yt_auto stats`。觀看時數和留存只能在 YouTube Studio 看到。
