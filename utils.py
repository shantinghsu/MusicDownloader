import csv
import logging
import shutil
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

import yt_dlp
from mutagen.id3 import APIC, ID3, TALB, TPE1, TIT2
from mutagen.mp3 import MP3

DOWNLOAD_DIR = Path("downloads")
HISTORY_FILE = Path("history.csv")
LOG_FILE = Path("app.log")
HISTORY_COLUMNS = ["下載時間", "歌曲名稱", "原始網址"]

ITUNES_AUTO_IMPORT_DIRS = [
  Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to iTunes",
  Path.home() / "Music" / "Apple Music" / "Automatically Add to Apple Music",
]

_logger = logging.getLogger("music_downloader")


# 設定 logging 模組，將所有日誌以繁體中文格式寫入本地 app.log 檔案。
def setup_logging() -> None:
  if _logger.handlers:
    return

  _logger.setLevel(logging.INFO)

  handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
  handler.setLevel(logging.INFO)
  handler.setFormatter(
    logging.Formatter(
      "%(asctime)s [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )
  )

  _logger.addHandler(handler)


# 從 yt-dlp 回傳的資訊中解析歌曲名稱、藝人與顯示用標題（歌曲-藝人）。
def parse_song_info(info: dict) -> tuple[str, str, str]:
  title = info.get("title", "未知歌曲")
  artist = info.get("artist") or info.get("uploader") or info.get("channel") or "未知藝人"
  song = title

  for separator in [" - ", " – ", "｜", "|"]:
    if separator in title:
      left, right = title.split(separator, 1)
      artist = left.strip()
      song = right.strip()
      break

  display_name = f"{song}-{artist}"
  return display_name, song, artist


# 取得 YouTube 影片縮圖網址，供寫入 MP3 封面使用。
def get_thumbnail_url(info: dict) -> str | None:
  thumbnails = info.get("thumbnails") or []
  if not thumbnails:
    return None
  return thumbnails[-1].get("url")


# 將歌曲標題、藝人與封面圖寫入 MP3 檔案的 ID3 標籤。
def embed_mp3_metadata(
  file_path: Path,
  song: str,
  artist: str,
  thumbnail_url: str | None,
) -> None:
  audio = MP3(file_path, ID3=ID3)
  if audio.tags is None:
    audio.add_tags()

  audio.tags.delall("TIT2")
  audio.tags.delall("TPE1")
  audio.tags.delall("TALB")
  audio.tags.delall("APIC")

  audio.tags.add(TIT2(encoding=3, text=song))
  audio.tags.add(TPE1(encoding=3, text=artist))
  audio.tags.add(TALB(encoding=3, text=artist))

  if thumbnail_url:
    with urlopen(thumbnail_url, timeout=15) as response:
      cover_data = response.read()
    audio.tags.add(
      APIC(
        encoding=3,
        mime="image/jpeg",
        type=3,
        desc="Cover",
        data=cover_data,
      )
    )

  audio.save()


# 尋找或建立 iTunes／Apple Music 的自動匯入資料夾。
def get_itunes_auto_import_dir() -> Path:
  for folder in ITUNES_AUTO_IMPORT_DIRS:
    if folder.is_dir():
      return folder

  for folder in ITUNES_AUTO_IMPORT_DIRS:
    try:
      folder.mkdir(parents=True, exist_ok=True)
      return folder
    except OSError:
      continue

  raise FileNotFoundError("找不到 iTunes／Apple Music 自動匯入資料夾")


# 將 MP3 複製到 iTunes 自動匯入資料夾，由 iTunes 自動加入媒體庫。
def import_to_itunes(mp3_path: Path) -> Path:
  import_dir = get_itunes_auto_import_dir()
  destination = import_dir / mp3_path.name

  if destination.exists():
    stem = mp3_path.stem
    suffix = mp3_path.suffix
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination = import_dir / f"{stem}_{timestamp}{suffix}"

  shutil.copy2(mp3_path, destination)
  return destination


# 使用 yt-dlp 下載指定 YouTube 網址的影音，並自動轉檔成最高音質的 MP3。
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
    _logger.info("1. 開始下載：%s", url)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=False)
      display_name, song, artist = parse_song_info(info)
      thumbnail_url = get_thumbnail_url(info)

      _logger.info("2. 歌曲資訊獲取成功：%s", display_name)
      _logger.info("3. 歌曲資訊確認......")

      if not song or not artist:
        raise ValueError("歌曲資訊不完整，無法繼續下載")

      _logger.info("4. 歌曲資訊已確認")
      _logger.info("5. 歌曲資訊打包至mp3檔......")

      ydl.extract_info(url, download=True)

    safe_title = yt_dlp.utils.sanitize_filename(info.get("title", song), restricted=True)
    file_path = DOWNLOAD_DIR / f"{safe_title}.mp3"

    if not file_path.exists():
      mp3_files = list(DOWNLOAD_DIR.glob("*.mp3"))
      if not mp3_files:
        raise FileNotFoundError("找不到轉檔後的 MP3 檔案")
      file_path = max(mp3_files, key=lambda path: path.stat().st_mtime)

    embed_mp3_metadata(file_path, song, artist, thumbnail_url)
    _logger.info("6. 歌曲資訊已打包至mp3檔")
    _logger.info("7. mp3存入downloads成功")

    _logger.info("8. 導入mp3至itunes自動匯入資料夾......")
    import_to_itunes(file_path)
    _logger.info("9. 導入成功")

    return display_name, str(file_path)

  except Exception as exc:
    _logger.error("下載失敗：%s | 錯誤：%s", url, exc)
    raise


# 將下載紀錄追加寫入 history.csv，欄位包含下載時間、歌曲名稱與原始網址。
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

  _logger.info("[Done] 已寫入歷史紀錄：%s", title)


# 讀取 history.csv 中的所有下載歷史紀錄，若檔案不存在則回傳空列表。
def read_history() -> list[dict[str, str]]:
  if not HISTORY_FILE.exists() or HISTORY_FILE.stat().st_size == 0:
    return []

  with HISTORY_FILE.open("r", encoding="utf-8-sig", newline="") as csv_file:
    return list(csv.DictReader(csv_file))


# 讀取 app.log 的最後 N 行內容，供側邊欄顯示開發者日誌。
def read_last_log_lines(line_count: int = 10) -> list[str]:
  if not LOG_FILE.exists():
    return ["（尚無日誌）"]

  lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
  if not lines:
    return ["（尚無日誌）"]

  return lines[-line_count:]


setup_logging()
