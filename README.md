# yt-auto：LittleFire 小火

YouTube 頻道 [LittleFire 小火](https://www.youtube.com/@Mander_kun) 的製作中心。

主角是原創角色**阿炭**：一塊脾氣火爆的小木炭，在台灣夜市學做小吃。每支 Shorts 20–30 秒、沒有對白，畫面用 AI 影片工具生成，剪輯、字幕、配樂和上傳資料由這個 repo 的程式處理。

- 📈 經營策略、收益路線圖、頻道改造清單：[`channel/strategy.md`](channel/strategy.md)
- 🎨 角色設定：[`channel/character_sheet.png`](channel/character_sheet.png)、[`channel/character.yaml`](channel/character.yaml)
- 🎬 前 10 集腳本（2026/10/24 起，每週二、四、六 18:00）：[`episodes/`](episodes/)

```
channel/      角色、策略（給人看）＋ character.yaml（給程式和 AI 工具用）
episodes/     一集一個 YAML：分鏡、AI prompt、字幕、YouTube 標題說明標籤
yt_auto/      產線程式
media/        你放 AI 片段和配樂的地方（不進 git）
build/        程式輸出的 prompt 表、成片、上傳清單（不進 git）
reports/      每週頻道週報
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

## 做一集的流程

**第一次開工：先做定裝照。** 打開 `channel/character.yaml`，複製 `prompt.reference_sheet` 和 `prompt.character` 到 AI 圖片工具，把 `channel/character_sheet.png` 當草圖丟進去。挑一張最滿意的，存成 `media/reference/a-tan.png`，之後每個鏡頭都用它當參考圖，阿炭才會集集長得一樣。

之後每一集：

1. `python -m yt_auto prompts ep01`：產生 `build/ep01/prompts.md`，裡面是逐鏡頭的英文 prompt。
2. 在 AI 影片工具選 9:16，上傳定裝照，逐鏡頭生成。每個鏡頭挑最好的一版，存成 `media/ep01/s01.mp4`、`s02.mp4`…
3. （選用）到 YouTube 音效庫下載配樂放進 `media/music/`，在集數 YAML 的 `music.file` 填 `music/檔名.mp3`。
4. `python -m yt_auto build ep01`：自動裁成 1080×1920，接起來，燒進中英字幕，混入配樂。輸出 `build/ep01/ep01.mp4` 和 `build/ep01/upload.md`。
5. 照 `upload.md` 在 YouTube Studio 上傳、排程（標題、說明、標籤、英文翻譯、設定都整理好了，複製貼上即可）。

片段還沒生完、想先看節奏：`python -m yt_auto build ep01 --placeholder`，缺的鏡頭會用灰底加畫面說明代替。

## 指令

| 指令 | 用途 |
|---|---|
| `python -m yt_auto list` | 所有集數的發布時間、片段進度、是否已剪好、是否已上傳 |
| `python -m yt_auto validate` | 檢查腳本和 metadata（長度限制、禁用字、標籤長度…） |
| `python -m yt_auto prompts ep01`／`all` | 輸出逐鏡頭 AI prompt 表 |
| `python -m yt_auto build ep01 [--placeholder] [--music 檔案]` | 剪成片＋上傳清單 |
| `python -m yt_auto compile ep01 … ep10 --name vol1` | 把多支 Shorts 接成 16:9 合集，附章節時間 |
| `python -m yt_auto upload ep01 [--dry-run]` | 用 YouTube API 上傳並排程（見下方限制） |
| `python -m yt_auto stats` | 產生頻道週報到 `reports/` |
| `python -m pytest` | 跑測試 |

## 寫新的一集

複製一個 `episodes/epXX-*.yaml` 改內容就好，再跑 `python -m yt_auto validate`。寫之前先看 [`channel/strategy.md`](channel/strategy.md) 的「不真實內容自我檢查」，出包方式和結局要跟前幾集不一樣。

YAML 小提醒：文字裡有 ` #`（空白加井號）或 `: `（冒號加空白）時，整段要用雙引號包起來，不然會被截斷。

也可以直接請 Claude 寫：「照 channel/strategy.md 的題材表，寫 EP11–EP20 的腳本」。

## 自動上傳（選用）

YouTube 有個限制：**用自己建立、還沒通過 YouTube 審核的 API 專案上傳，影片會被鎖在「私人」**。所以一開始用 `upload.md` 手動上傳最實際。想自動化的話：

1. [Google Cloud Console](https://console.cloud.google.com/) 建立專案，啟用 **YouTube Data API v3**。
2. 「OAuth 同意畫面」選外部，把自己的 Google 帳號加進測試使用者。
3. 「憑證」→ 建立 OAuth 用戶端 ID → 類型選「電腦版應用程式」，下載 JSON 存成 `.secrets/client_secret.json`。
4. `python -m yt_auto upload ep01 --dry-run` 確認內容，再拿掉 `--dry-run` 正式上傳。第一次會開瀏覽器登入。
5. 送出 [YouTube API 稽核表單](https://support.google.com/youtube/contact/yt_api_form)，通過後上傳的影片才能公開或排程。

## 週報

`stats` 只讀公開資料，用 API 金鑰就好，不需要登入：

1. 同一個 Google Cloud 專案 →「憑證」→ 建立 API 金鑰（建議限制只能用 YouTube Data API v3）。
2. `export YOUTUBE_API_KEY=你的金鑰`，然後 `python -m yt_auto stats`。

觀看時數和 Shorts 90 天觀看數只能在 YouTube Studio 看到，週報裡的是近似值。
