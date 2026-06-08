import streamlit as st

from utils import (
  append_to_history,
  download_mp3_from_youtube,
  read_history,
  read_last_log_lines,
)

st.set_page_config(page_title="音樂下載中心", layout="wide")

st.title("🎵 個人音樂自動化下載中心")

url = st.text_input(
  "貼上 YouTube 網址",
  placeholder="https://www.youtube.com/watch?v=...",
)

if st.button("🚀 開始下載並記錄", type="primary", width="stretch"):
  if not url.strip():
    st.warning("請輸入 YouTube 網址")
  else:
    try:
      with st.spinner("正在下載、寫入標籤並匯入 iTunes，請稍候..."):
        progress = st.progress(0, text="1. 開始下載...")
        progress.progress(20, text="2. 獲取歌曲資訊...")
        title, _file_path = download_mp3_from_youtube(url.strip())
        progress.progress(85, text="9. 匯入 iTunes 完成，寫入歷史紀錄...")
        append_to_history(title, url.strip())
        progress.progress(100, text="[Done] 全部完成！")
      st.success(f"下載並匯入成功！歌曲：{title}")
    except Exception as exc:
      st.error(f"下載失敗：{exc}")

st.divider()
st.subheader("📋 下載歷史紀錄")

history_rows = read_history()
if history_rows:
  st.dataframe(history_rows, width="stretch")
else:
  st.info("目前尚無下載紀錄。")

with st.sidebar:
  st.header("🔧 開發者 Log")
  st.caption("顯示 app.log 最後 15 行")
  log_lines = read_last_log_lines(15)
  st.code("\n".join(log_lines), language="text")
