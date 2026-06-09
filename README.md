# MusicDownloader

A local web app to download YouTube music and sync to iTunes.

This is a vibe coding program to help me conveniently download music from YouTube to my Apple Music app.
For the initial version, it will be in Mandarin.

# 🎵 YT音樂下載與iTunes自動同步工具

一個以 Python 打造的本地網頁應用，讓使用者透過瀏覽器貼上 YouTube 網址，即可自動下載影音、轉檔為高品質 MP3，並記錄下載歷史與執行日誌。
本專案為個人作品集專案，目標是展示全端開發能力與自動化工作流程設計。

---

## 專案概述

**音樂下載與自動同步工具**（Music Downloader）解決了「從 YouTube 取得音樂並整理到本地媒體庫」這一常見需求。使用者無需熟悉命令列，只要在網頁介面貼上連結、點擊按鈕，系統便會：

1. 呼叫 `yt-dlp` 擷取指定影片或播放清單的音訊串流
2. 透過 FFmpeg 自動轉檔為最高音質的 MP3，並以 Mutagen 寫入 ID3 標籤與封面
3. 依自訂資料夾與檔名格式儲存 MP3，並自動匯入 iTunes／Apple Music
4. 將下載時間、歌曲名稱與原始網址寫入 `history.csv`
5. 以繁體中文格式將操作過程記錄至 `app.log`，並在側邊欄即時顯示最後 15 行日誌

### 主要功能

- **一鍵下載**：貼上 YouTube 單曲或播放清單網址即可下載並轉檔
- **中繼資料寫入**：自動嵌入歌曲標題、藝人與專輯封面至 MP3
- **iTunes 同步**：下載完成後自動複製至 iTunes／Apple Music 自動匯入資料夾
- **自訂輸出**：側邊欄可設定輸出資料夾與檔名格式（歌曲-藝人、藝人 - 歌曲、原始標題）
- **播放清單批次下載**：支援整份 YouTube 播放清單一次下載
- **進度回饋**：下載過程顯示 Spinner 與進度條
- **歷史紀錄**：網頁底部以表格呈現所有下載紀錄
- **開發者日誌**：側邊欄即時預覽 `app.log`，方便錯誤排查

### 專案結構

```
MusicDownloader/
├── app.py              # Streamlit 網頁介面
├── utils.py            # 核心功能模組（下載、紀錄、日誌）
├── requirements.txt    # Python 相依套件
├── settings.json       # 使用者下載設定（執行時自動建立）
├── downloads/          # 預設 MP3 輸出目錄（執行時自動建立）
├── history.csv         # 下載歷史紀錄（執行時自動建立）
└── app.log             # 執行日誌（執行時自動建立）
```

---

## 技術棧


| 類別   | 技術                                              | 用途                |
| ---- | ----------------------------------------------- | ----------------- |
| 程式語言 | Python 3                                        | 後端邏輯與自動化腳本        |
| 網頁框架 | [Streamlit](https://streamlit.io/)              | 本地網頁 UI，快速建構互動式介面 |
| 影音下載 | [yt-dlp](https://github.com/yt-dlp/yt-dlp)      | 擷取 YouTube 音訊串流   |
| 音訊轉檔 | FFmpeg                                          | 將音訊轉換為 MP3 格式     |
| 中繼資料 | [mutagen](https://github.com/quodlibet/mutagen) | MP3 ID3 標籤與封面寫入      |
| 日誌   | Python `logging`                                | 繁體中文結構化日誌輸出       |
| 資料儲存 | CSV（`csv` 模組）                                   | 輕量級下載歷史紀錄         |


---

## 快速開始

### 前置需求

- Python 3.10 以上
- [FFmpeg](https://ffmpeg.org/download.html)（MP3 轉檔必備）

```powershell
# Windows 安裝 FFmpeg（擇一）
winget install Gyan.FFmpeg
```

### 安裝與啟動

```powershell
# 1. 複製專案
git clone https://github.com/shantinghsu/music-downloader.git
cd music-downloader

# 2. 建立並啟動虛擬環境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. 安裝相依套件
pip install -r requirements.txt

# 4. 啟動網頁應用
streamlit run app.py
```

瀏覽器將自動開啟 `http://localhost:8501`。

---

## 開發路線圖（TODO List）

以下為專案五個主要開發階段的檢核表，依序推進功能完善與作品集展示需求。

### 階段一：核心下載引擎

- [x] 整合 `yt-dlp`，支援 YouTube 單曲下載
- [x] 透過 FFmpeg 自動轉檔為最高音質 MP3
- [x] 建立 `downloads/` 輸出目錄與檔名清理機制
- [x] 以 `try-except` 包裹下載流程，失敗時記錄錯誤並拋出異常

### 階段二：網頁介面與使用者體驗

- [x] 使用 Streamlit 建立本地網頁應用
- [x] 實作 URL 輸入框與「開始下載並記錄」按鈕
- [x] 下載過程顯示 Spinner 與進度條
- [x] 成功／失敗時分別顯示綠色與紅色提示訊息

### 階段三：紀錄與日誌系統

- [x] 設定 `logging` 模組，繁體中文日誌寫入 `app.log`
- [x] 實作 `history.csv` 自動建立與追加寫入
- [x] 網頁底部以表格顯示完整下載歷史
- [x] 側邊欄即時顯示 `app.log` 最後 10 行

### 階段四：媒體庫整合與中繼資料

- [x] 使用 `mutagen` 寫入 MP3 ID3 標籤（標題、藝人、專輯封面）
- [x] 自動同步下載的 MP3 至 iTunes／Apple Music 媒體庫
- [x] 支援自訂輸出資料夾與檔名格式
- [x] 支援播放清單（Playlist）批次下載

### 階段五：品質提升與作品集完善

- [ ] 撰寫單元測試，涵蓋下載、紀錄與日誌模組
- [x] 新增 `.gitignore`，排除 `venv/`、`downloads/`、日誌等執行時檔案
- [ ] 改善錯誤訊息與使用者操作引導（如 FFmpeg 未安裝提示）
- [ ] 部署示範環境或錄製操作 Demo，供 UC 轉學申請作品集展示

---

## 授權

