import streamlit as st

from utils import (
  DownloadConfig,
  SongMetadata,
  append_to_history,
  crop_max_square,
  download_confirmed_tracks,
  is_playlist_url,
  load_settings,
  preview_youtube_tracks,
  read_history,
  save_settings,
  is_duplicate_download,
)

FILENAME_FORMAT_OPTIONS = {
  "歌曲 - 藝人（七里香 - 周杰倫）": "song - artist",
  "藝人 - 歌曲（周杰倫 - 七里香）": "artist - song",
  "YouTube 原始標題": "title",
}

st.set_page_config(page_title="音樂下載中心", layout="wide")

if "track_previews" not in st.session_state:
  st.session_state.track_previews = None

st.title("🎵 個人音樂自動化下載中心")

saved_settings = load_settings()

try:
  default_format_index = list(FILENAME_FORMAT_OPTIONS.values()).index(
    saved_settings.filename_format
  )
except ValueError:
  default_format_index = 0


def build_download_config() -> DownloadConfig:
  format_label = st.session_state.get("format_label", list(FILENAME_FORMAT_OPTIONS.keys())[0])
  filename_format = FILENAME_FORMAT_OPTIONS.get(
    format_label,
    list(FILENAME_FORMAT_OPTIONS.values())[default_format_index],
  )
  return DownloadConfig(
    download_dir=st.session_state.get("download_dir", str(saved_settings.download_dir)),
    filename_format=filename_format,
  )


with st.sidebar:
  st.header("⚙️ 下載設定")
  download_dir = st.text_input(
    "輸出資料夾",
    value=str(saved_settings.download_dir),
    help="MP3 檔案下載後的存放路徑",
    key="download_dir",
  )
  format_label = st.selectbox(
    "檔名格式",
    options=list(FILENAME_FORMAT_OPTIONS.keys()),
    index=default_format_index,
    key="format_label",
  )
  batch_playlist = st.checkbox(
    "播放清單批次下載",
    value=True,
    help="貼上播放清單網址時，解析並下載清單內所有歌曲",
    key="batch_playlist",
  )

  if st.button("儲存設定", width='stretch'):
    save_settings(build_download_config())
    st.success("設定已儲存")


with st.form("youtube_url_form", clear_on_submit=False):
  st.caption("在網址輸入框貼上連結後，按 Enter 或點擊按鈕即可開始解析。")
  url_input = st.text_input(
    "貼上 YouTube 網址",
    placeholder="https://www.youtube.com/watch?v=... 或播放清單網址",
    label_visibility="collapsed",
  )
  parse_submitted = st.form_submit_button(
    "🚀 開始下載並記錄",
    type="primary",
    width='stretch',
  )

if parse_submitted:
  if not url_input.strip():
    st.warning("請輸入 YouTube 網址")
    st.session_state.track_previews = None
  else:
    config = build_download_config()
    save_settings(config)

    try:
      with st.spinner("正在解析歌曲資訊，請稍候..."):
        st.session_state.track_previews = preview_youtube_tracks(
          url_input.strip(),
          batch_playlist=batch_playlist,
        )
    except Exception as exc:
      st.error(f"解析失敗：{exc}")
      st.session_state.track_previews = None

if url_input.strip() and is_playlist_url(url_input.strip()) and batch_playlist:
  st.info("偵測到播放清單網址。解析後可逐一預覽並編輯每首歌曲的元資料。")

if st.session_state.track_previews:
  previews: list[SongMetadata] = st.session_state.track_previews
  is_batch = len(previews) > 1

  st.divider()
  st.subheader("📝 元資料預覽與編輯")
  st.caption("請確認或修改以下資訊，完成後點擊「確認下載並匯入」才會開始正式下載。")

  confirmed_tracks: list[SongMetadata] = []

  for index, preview in enumerate(previews):
      container = st.expander(
          f"第 {index + 1} 首：{preview.display_name}",
          expanded=not is_batch or index == 0,
      ) if is_batch else st.container()

      with container:
          cover_col, form_col = st.columns([1, 2], gap="large")

          thumbnail_default = preview.thumbnail_url or ""
          thumbnail_key = f"preview_thumbnail_{index}_{preview.url}"

          with form_col:
              song = st.text_input(
                  "歌名",
                  value=preview.song,
                  key=f"preview_song_{index}_{preview.url}",
              )
              artist = st.text_input(
                  "歌手",
                  value=preview.artist,
                  key=f"preview_artist_{index}_{preview.url}",
              )
              thumbnail_url = st.text_input(
                  "封面圖網址",
                  value=thumbnail_default,
                  help="可貼上其他圖片網址以替換預設封面",
                  key=thumbnail_key,
              )

          with cover_col:
              st.markdown("**專輯封面預覽**")
              current_thumbnail = st.session_state.get(thumbnail_key, thumbnail_default)

              if current_thumbnail.strip():
                  cropped_image = crop_max_square(current_thumbnail.strip())
                  st.image(
                      cropped_image if cropped_image is not None else current_thumbnail.strip(),
                      width=220,
                  )
              else:
                  st.info("尚未設定封面圖網址")

          confirmed_tracks.append(
              SongMetadata(
                  url=preview.url,
                  song=song.strip() or preview.song,
                  artist=artist.strip() or preview.artist,
                  thumbnail_url=thumbnail_url.strip() or None,
                  original_title=preview.original_title,
              )
          )

  confirm_col, cancel_col = st.columns([3, 1])
  with confirm_col:
    confirm_download = st.button(
      "✅ 確認下載並匯入",
      type="primary",
      width='stretch',
    )
  with cancel_col:
    if st.button("取消", width='stretch'):
      st.session_state.track_previews = None
      st.rerun()

  if confirm_download:
    invalid_tracks = [
      track for track in confirmed_tracks if not track.song.strip() or not track.artist.strip()
    ]
    if invalid_tracks:
      st.error("歌名與歌手不可為空，請補齊後再確認下載。")
    else:
      config = build_download_config()
      save_settings(config)

      # 初始化兩個陣列，將歌曲分流處理
      tracks_to_download = []  # 存放真正需要下載的歌
      duplicate_tracks = []    # 存放重複的歌，稍後用來提示
      
      # 逐一檢查播放清單中的每首歌曲
      for track in confirmed_tracks:
          if is_duplicate_download(url=track.url, song=track.song, artist=track.artist):
              duplicate_tracks.append(track)  # 重複的，丟進歷史區
          else:
              tracks_to_download.append(track) # 乾淨的，留下來下載
      
      if duplicate_tracks:
          duplicate_names = [f"{track.song} - {track.artist}" for track in duplicate_tracks]
          st.warning(f"以下歌曲已存在於下載歷史中，請勿重複下載：\n{', '.join(duplicate_names)}")

      try:
        with st.spinner("正在下載、寫入標籤並匯入 iTunes，請稍候..."):
          progress = st.progress(0, text="1. 開始下載...")
          progress.progress(20, text="2. 依確認後的元資料下載中...")

          results = download_confirmed_tracks(tracks_to_download, config=config)

          for index, (title, _file_path, video_url) in enumerate(results, start=1):
            progress.progress(
              85,
              text=f"寫入歷史紀錄 {index}/{len(results)}...",
            )
            append_to_history(title, video_url)

          progress.progress(100, text="[Done] 全部完成！")

        st.session_state.track_previews = None

        if len(results) == 1:
          st.success(f"下載並匯入成功！歌曲：{results[0][0]}")
        else:
          st.success(f"批次下載完成！共 {len(results)} 首歌曲已匯入 iTunes。")
      except Exception as exc:
        st.error(f"下載失敗：{exc}")

st.divider()
st.subheader("📋 下載歷史紀錄")

history_rows = read_history()
if history_rows:
  st.dataframe(history_rows, width='stretch')
else:
  st.info("目前尚無下載紀錄。")
