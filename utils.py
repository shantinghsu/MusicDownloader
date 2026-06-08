import csv
import logging
from datetime import datetime
from pathlib import Path

import yt_dlp

DOWNLOAD_DIR = Path("downloads")
HISTORY_FILE = Path("history.csv")
LOG_FILE = Path("app.log")
HISTORY_COLUMNS = ["下載時間", "歌曲名稱", "原始網址"]

_logger = logging.getLogger("music_downloader")


def setup_logging() -> None:
  if _logger.handlers:
    return

  _logger.setLevel(logging.INFO)

  handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
  handler.setLevel(logging.INFO)
  handler.setFormatter(
    logging.Formatter(
      "%(asctime)s | %(levelname)s | %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )
  )

  _logger.addHandler(handler)


def download_mp3_from_youtube(url: str) -> tuple[str, str]:
  setup_logging()
  DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

  ydl_opts = {
    "format": "bestaudio/best",
    "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
    "postprocessors": [
      {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "0",
      }
    ],
    "quiet": True,
    "no_warnings": True,
  }

  try:
    _logger.info("開始下載：%s", url)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=False)
      title = info.get("title", "未知歌曲")
      ydl.extract_info(url, download=True)

    safe_title = yt_dlp.utils.sanitize_filename(title, restricted=True)
    file_path = DOWNLOAD_DIR / f"{safe_title}.mp3"

    if not file_path.exists():
      mp3_files = list(DOWNLOAD_DIR.glob("*.mp3"))
      if not mp3_files:
        raise FileNotFoundError("找不到轉檔後的 MP3 檔案")
      file_path = max(mp3_files, key=lambda path: path.stat().st_mtime)

    _logger.info("轉檔成功：%s", title)
    return title, str(file_path)

  except Exception as exc:
    _logger.error("下載失敗：%s | 錯誤：%s", url, exc)
    raise


def append_to_history(title: str, url: str) -> None:
  setup_logging()
  row = {
    "下載時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "歌曲名稱": title,
    "原始網址": url,
  }

  file_exists = HISTORY_FILE.exists() and HISTORY_FILE.stat().st_size > 0

  with HISTORY_FILE.open("a", encoding="utf-8-sig", newline="") as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=HISTORY_COLUMNS)
    if not file_exists:
      writer.writeheader()
    writer.writerow(row)

  _logger.info("已寫入歷史紀錄：%s", title)


def read_history() -> list[dict[str, str]]:
  if not HISTORY_FILE.exists() or HISTORY_FILE.stat().st_size == 0:
    return []

  with HISTORY_FILE.open("r", encoding="utf-8-sig", newline="") as csv_file:
    return list(csv.DictReader(csv_file))


def read_last_log_lines(line_count: int = 10) -> list[str]:
  if not LOG_FILE.exists():
    return ["（尚無日誌）"]

  lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
  if not lines:
    return ["（尚無日誌）"]

  return lines[-line_count:]


setup_logging()
