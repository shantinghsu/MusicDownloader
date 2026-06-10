import csv
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests
import yt_dlp
from mutagen.id3 import APIC, ID3, TALB, TPE1, TIT2
from mutagen.mp3 import MP3
from PIL import Image

DEFAULT_DOWNLOAD_DIR = Path("downloads")
HISTORY_FILE = Path("history.csv")
LOG_FILE = Path("app.log")
SETTINGS_FILE = Path("settings.json")
HISTORY_COLUMNS = ["下載時間", "歌曲名稱", "原始網址"]

FILENAME_FORMATS = {
  "song - artist": "{song} - {artist}",
  "artist - song": "{artist} - {song}",
  "title": "{title}",
}

LEGACY_FILENAME_FORMATS = {
  "song-artist": "song - artist",
  "artist-song": "artist - song",
}

ITUNES_MEDIA_BASES = [
  Path.home() / "Music" / "iTunes" / "iTunes Media",
  Path.home() / "Music" / "Apple Music",
]

POSSIBLE_AUTO_IMPORT_NAMES = [
  "自動加入 iTunes",
  "Automatically Add to iTunes",
  "自动加入 iTunes",
  "Automatically Add to Apple Music",
  "自動加入 Apple Music",
]

_logger = logging.getLogger("music_downloader")

YDL_QUIET_OPTS = {
  "quiet": True,
  "no_warnings": True,
}


@dataclass
class DownloadConfig:
  download_dir: Path = DEFAULT_DOWNLOAD_DIR
  filename_format: str = "song - artist"

  def __post_init__(self):
    if isinstance(self.download_dir, str):
      self.download_dir = Path(self.download_dir)
    self.filename_format = normalize_filename_format(self.filename_format)
    self.download_dir = self.download_dir.expanduser().resolve()
  def build_filename(self, song: str, artist: str, title: str) -> str:
    template = FILENAME_FORMATS.get(self.filename_format, FILENAME_FORMATS["song - artist"])
    filename = template.format(song=song, artist=artist, title=title)
    safe_name = yt_dlp.utils.sanitize_filename(filename, restricted=False)
    return f"{safe_name}.mp3"


@dataclass
class SongMetadata:
  url: str
  song: str
  artist: str
  thumbnail_url: str | None
  original_title: str

  @property
  def display_name(self) -> str:
    return f"{self.song}-{self.artist}"


def _download_cover_image(url: str) -> Image.Image | None:
  try:
    response = requests.get(
      url,
      timeout=15,
      headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    image.load()
    return image
  except Exception:
    return None

# 專輯封面預覽靠左置中
def _crop_center_square(image: Image.Image) -> Image.Image:
  width, height = image.size
  side = min(width, height)
  left = (width - side) // 2
  top = (height - side) // 2
  return image.crop((left, top, left + side, top + side))

# 專輯封面轉檔至jepq格式
def _image_to_jpeg_bytes(image: Image.Image) -> bytes | None:
  if image.mode in ("RGBA", "LA", "P"):
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.split()[-1])
    image = background
  elif image.mode != "RGB":
    image = image.convert("RGB")

  buffer = BytesIO()
  image.save(buffer, format="JPEG", quality=95, subsampling=0)
  cover_data = buffer.getvalue()

  if not cover_data.startswith(b"\xff\xd8"):
    return None

  return cover_data


def crop_max_square(url: str):
  image = _download_cover_image(url)
  if image is None:
    return None

  try:
    return _crop_center_square(image)
  except Exception:
    return None


# 下載並裁切封面圖，轉為真正的 JPEG 二進位資料供 APIC 標籤寫入。
def prepare_cover_bytes(thumbnail_url: str) -> bytes | None:
  setup_logging()

  try:
    image = _download_cover_image(thumbnail_url)
    if image is None:
      _logger.warning("封面圖下載失敗：%s", thumbnail_url)
      return None

    square_image = _crop_center_square(image)
    cover_data = _image_to_jpeg_bytes(square_image)
    if cover_data is None:
      _logger.warning("封面圖 JPEG 轉換失敗：%s", thumbnail_url)
      return None

    return cover_data
  except Exception as exc:
    _logger.warning("prepare_cover_bytes 失敗：%s | 錯誤：%s", thumbnail_url, exc)
    return None


# 將舊版或無效的 filename_format 正規化為程式支援的 key。
def normalize_filename_format(filename_format: str) -> str:
  if filename_format in FILENAME_FORMATS:
    return filename_format
  return LEGACY_FILENAME_FORMATS.get(filename_format, "song - artist")


# 正規化下載設定，確保輸出目錄為絕對路徑且資料夾已建立。
def normalize_download_config(config: DownloadConfig | None = None) -> DownloadConfig:
  if config is None:
    config = load_settings()
  elif isinstance(config, (str, Path)):
    config = DownloadConfig(download_dir=Path(config))
  elif not isinstance(config, DownloadConfig):
    config = load_settings()
  else:
    config = DownloadConfig(
      download_dir=config.download_dir,
      filename_format=config.filename_format,
    )

  config.download_dir.mkdir(parents=True, exist_ok=True)
  return config


# 從 yt-dlp 下載結果中取得實際產出的 MP3 檔案路徑。
def resolve_downloaded_mp3_path(ydl: yt_dlp.YoutubeDL, info: dict, download_dir: Path) -> Path:
  requested_downloads = info.get("requested_downloads") or []
  for item in requested_downloads:
    filepath = item.get("filepath")
    if filepath:
      candidate = Path(filepath)
      if candidate.suffix.lower() == ".mp3" and candidate.exists():
        return candidate.resolve()

  for candidate in (
    Path(ydl.prepare_filename(info, ext="mp3")),
    download_dir / f"{yt_dlp.utils.sanitize_filename(info.get('title', 'unknown'), restricted=False)}.mp3",
  ):
    if candidate.exists():
      return candidate.resolve()

  raise FileNotFoundError(
    f"找不到轉檔後的 MP3 檔案（預期目錄：{download_dir.resolve()}）"
  )


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


# 讀取使用者自訂的下載設定（輸出資料夾與檔名格式）。
def load_settings() -> DownloadConfig:
  if not SETTINGS_FILE.exists():
    return DownloadConfig()

  try:
    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError):
    return DownloadConfig()

  return DownloadConfig(
    download_dir=Path(data.get("download_dir", DEFAULT_DOWNLOAD_DIR)),
    filename_format=normalize_filename_format(
      data.get("filename_format", "song - artist")
    ),
  )


# 儲存使用者自訂的下載設定至 settings.json。
def save_settings(config: DownloadConfig) -> None:
  payload = {
    "download_dir": str(config.download_dir),
    "filename_format": config.filename_format,
  }
  SETTINGS_FILE.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )


# 判斷網址是否為 YouTube 播放清單。
def is_playlist_url(url: str) -> bool:
  return "list=" in url and (
    "playlist" in url
    or re.search(r"youtube\.com/playlist", url) is not None
  )


# 從 YouTube 播放清單或單曲網址取得待下載的影片網址列表。
def get_video_urls(url: str, batch_playlist: bool = False) -> list[str]:
  if not batch_playlist and not is_playlist_url(url):
    return [url]

  ydl_opts = {
    "extract_flat": "in_playlist",
    **YDL_QUIET_OPTS,
  }

  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)

  if info.get("_type") != "playlist":
    return [url]

  video_urls: list[str] = []
  for entry in info.get("entries") or []:
    if not entry:
      continue
    video_id = entry.get("id") or entry.get("url")
    if not video_id:
      continue
    if video_id.startswith("http"):
      video_urls.append(video_id)
    else:
      video_urls.append(f"https://www.youtube.com/watch?v={video_id}")

  return video_urls or [url]


# 從 yt-dlp 回傳的資訊中解析歌曲名稱、藝人與顯示用標題（歌曲 - 藝人）。
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

  display_name = f"{song} - {artist}"
  return display_name, song, artist


# 取得 YouTube 影片縮圖網址，供寫入 MP3 封面使用。
def get_thumbnail_url(info: dict) -> str | None:
  thumbnails = info.get("thumbnails") or []
  if not thumbnails:
    return None
  return thumbnails[-1].get("url")


# 使用 yt-dlp 預先解析單曲網址，取得元資料預覽資訊（不下載檔案）。
def fetch_song_metadata(url: str) -> SongMetadata:
  with yt_dlp.YoutubeDL(YDL_QUIET_OPTS) as ydl:
    info = ydl.extract_info(url, download=False)

  _display_name, song, artist = parse_song_info(info)
  return SongMetadata(
    url=url,
    song=song,
    artist=artist,
    thumbnail_url=get_thumbnail_url(info),
    original_title=info.get("title", song),
  )


# 預先解析單曲或播放清單內所有歌曲的元資料，供介面預覽與編輯。
def preview_youtube_tracks(url: str, batch_playlist: bool = False) -> list[SongMetadata]:
  setup_logging()
  video_urls = get_video_urls(url, batch_playlist=batch_playlist)
  previews = [fetch_song_metadata(video_url) for video_url in video_urls]

  if len(previews) > 1:
    _logger.info("[Preview] 播放清單解析完成，共 %s 首", len(previews))
  else:
    preview = previews[0]
    _logger.info("[Preview] 單曲解析完成：%s", preview.display_name)

  return previews


# 將歌曲標題、藝人與封面圖寫入 MP3 檔案的 ID3 標籤。
def embed_mp3_metadata(
  file_path: Path,
  song: str,
  artist: str,
  thumbnail_url: str | None,
) -> None:
  setup_logging()
  file_path = Path(file_path)
  audio = MP3(file_path, ID3=ID3)
  if audio.tags is None:
    audio.add_tags()

  audio.tags.delall("TIT2")
  audio.tags.delall("TPE1")
  audio.tags.delall("TALB")
  audio.tags.delall("APIC")

  audio.tags.add(TIT2(encoding=3, text=song))
  audio.tags.add(TPE1(encoding=3, text=artist))
  audio.tags.add(TALB(encoding=3, text=song))

  if thumbnail_url and thumbnail_url.strip():
    try:
      cover_data = prepare_cover_bytes(thumbnail_url.strip())
      if cover_data:
        audio.tags.add(
          APIC(
            encoding=0,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=cover_data,
          )
        )
        _logger.info("封面已成功寫入 APIC 標籤（JPEG，%s bytes）", len(cover_data))
      else:
        _logger.warning(
          "封面圖下載或裁切失敗，略過 APIC 標籤寫入：%s",
          thumbnail_url,
        )
    except Exception as exc:
      _logger.warning(
        "封面圖寫入失敗，略過 APIC 標籤：%s | 錯誤：%s",
        thumbnail_url,
        exc,
      )

  audio.save(v2_version=3)


# 依自訂檔名格式重新命名 MP3 檔案。
def rename_mp3_file(
  source_path: Path,
  config: DownloadConfig,
  song: str,
  artist: str,
  title: str,
) -> Path:
  source_path = source_path.resolve()
  destination = (config.download_dir / config.build_filename(song, artist, title)).resolve()
  if source_path.resolve() == destination.resolve():
    return destination

  if destination.exists():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination = destination.with_stem(f"{destination.stem}_{timestamp}")

  source_path.replace(destination)
  return destination

# 檢測歌曲是否重複下載
def is_duplicate_download(url=None, song=None, artist=None):
    """
    檢查是否存在重複的下載記錄。
    :param url: YouTube 影片的 URL
    :param song: 歌名
    :param artist: 歌手
    :return: 如果重複則返回 True，否則返回 False
    """
    if not HISTORY_FILE.exists():
        return False  # 如果歷史檔案不存在，直接返回 False

    with HISTORY_FILE.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            # 檢查 URL 是否重複
            if url and row.get("原始網址") == url:
                _logger.info("檢測到重複的歌曲（URL）：%s", url)
                return True

            # 檢查歌曲名稱和歌手是否重複（忽略大小寫）
            if song and artist:
                if row.get("歌曲名稱", "").strip().lower() == song.strip().lower():
                    _logger.info("檢測到重複的歌曲（歌曲名稱和歌手）：%s - %s", song, artist)
                    return True

    return False

# 具備國際化相容性的 iTunes 自動匯入資料夾偵測函式，優先尋找中文「自動加入 iTunes」。
def get_itunes_auto_import_dir() -> Path:
  for base in ITUNES_MEDIA_BASES:
    if base.is_dir():
      for name in POSSIBLE_AUTO_IMPORT_NAMES:
        folder = base / name
        if folder.is_dir():
          return folder

  for base in ITUNES_MEDIA_BASES:
    if base.is_dir():
      default_name = (
        "Automatically Add to Apple Music"
        if "Apple Music" in str(base)
        else "自動加入 iTunes"
      )
      target_folder = base / default_name
      try:
        target_folder.mkdir(parents=True, exist_ok=True)
        return target_folder
      except OSError:
        continue

  raise FileNotFoundError("找不到任何相容的 iTunes／Apple Music 媒體庫路徑")


# 將 MP3 複製到 iTunes 自動匯入資料夾，由 iTunes 自動加入媒體庫。
def import_to_itunes(mp3_path: Path) -> Path:
  import_dir = get_itunes_auto_import_dir()

  try:
    os.startfile(import_dir.resolve())
  except Exception as exc:
    _logger.warning("無法自動開啟資料夾: %s", exc)

  destination = import_dir / mp3_path.name

  if destination.exists():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination = import_dir / f"{mp3_path.stem}_{timestamp}{mp3_path.suffix}"

  shutil.copy2(mp3_path, destination)
  return destination


# 依使用者確認後的元資料正式下載 MP3、寫入標籤並匯入 iTunes。
def download_mp3_from_youtube(
  metadata: SongMetadata,
  config: DownloadConfig | None = None,
) -> tuple[str, str]:
  setup_logging()
  download_config = normalize_download_config(config)

  song = metadata.song.strip()
  artist = metadata.artist.strip()
  thumbnail_url = metadata.thumbnail_url.strip() if metadata.thumbnail_url else None
  display_name = f"{song} - {artist}"

  download_dir = download_config.download_dir
  ydl_opts = {
    "format": "bestaudio/best",
    "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
    "paths": {"home": str(download_dir), "temp": str(download_dir)},
    "postprocessors": [
      {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "0",
      }
    ],
    **YDL_QUIET_OPTS,
  }

  try:
    _logger.info("1. 開始下載：%s", metadata.url)
    _logger.info("2. 歌曲資訊獲取成功：%s", display_name)
    _logger.info("3. 歌曲資訊確認......")

    if not song or not artist:
      raise ValueError("歌曲資訊不完整，無法繼續下載")

    _logger.info("4. 歌曲資訊已確認")
    _logger.info("5. 歌曲資訊打包至mp3檔......")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(metadata.url, download=True)
      file_path = resolve_downloaded_mp3_path(ydl, info, download_dir)

    embed_mp3_metadata(file_path, song, artist, thumbnail_url)
    _logger.info("6. 歌曲資訊已打包至mp3檔")

    file_path = rename_mp3_file(
      file_path,
      download_config,
      song,
      artist,
      metadata.original_title,
    )
    _logger.info("7. mp3存入%s成功", download_config.download_dir)

    _logger.info("8. 導入mp3至itunes自動匯入資料夾......")
    import_to_itunes(file_path)
    _logger.info("9. 導入成功")

    return display_name, str(file_path)

  except Exception as exc:
    _logger.error("下載失敗：%s | 錯誤：%s", metadata.url, exc)
    raise


# 依使用者確認後的元資料批次下載並匯入 iTunes。
def download_confirmed_tracks(
  tracks: list[SongMetadata],
  config: DownloadConfig | None = None,
) -> list[tuple[str, str, str]]:
  setup_logging()
  download_config = normalize_download_config(config)

  if len(tracks) > 1:
    _logger.info("[Playlist] 開始批次下載，共 %s 首", len(tracks))

  results: list[tuple[str, str, str]] = []
  for index, track in enumerate(tracks, start=1):
    if len(tracks) > 1:
      _logger.info("[Playlist] 正在下載第 %s/%s 首", index, len(tracks))

    display_name, file_path = download_mp3_from_youtube(track, download_config)
    results.append((display_name, file_path, track.url))

  if len(tracks) > 1:
    _logger.info("[Playlist] 批次下載完成，共 %s 首", len(results))

  return results


# 批次下載 YouTube 單曲或播放清單，回傳每首歌曲的下載結果。
def download_youtube_batch(
  url: str,
  config: DownloadConfig | None = None,
  batch_playlist: bool = False,
) -> list[tuple[str, str, str]]:
  previews = preview_youtube_tracks(url, batch_playlist=batch_playlist)
  return download_confirmed_tracks(previews, config)


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


setup_logging()
