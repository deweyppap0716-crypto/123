import os
import sqlite3
from datetime import datetime
import streamlit as st
from google import genai
from google.genai import types

# --- DATABASE SETUP (Persistent Score Tracking & Leaderboard) ---
DB_NAME = "game_scores.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_score(player_name, score, category, difficulty):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO leaderboard (player_name, score, category, difficulty, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (player_name, score, category, difficulty, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def get_leaderboard(limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT player_name, score, category, difficulty, timestamp 
        FROM leaderboard 
        ORDER BY score DESC 
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# Initialize database on startup
init_db()

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="頭上文字猜猜樂 (Heads Up!)", 
    page_icon="🎮", 
    layout="centered"
)

st.title("🎮 頭上文字猜猜樂 (Heads Up!)")
st.markdown("由 **Google Gemini** 支援的互動猜字遊戲網頁版，具備排行榜與分數持久化功能！")

# --- SIDEBAR CONFIGURATION & LEADERBOARD ---
with st.sidebar:
    st.header("⚙️ 遊戲設定")
    
    api_key_input = st.text_input(
        "Gemini API Key", 
        value=os.environ.get("GEMINI_API_KEY", ""), 
        type="password",
        help="輸入您的 Google Gemini API Key"
    )
    
    category = st.selectbox(
        "選擇主題類別",
        ["日常物品與食物", "動漫/遊戲角色", "歷史人物/偉人", "動物與生物", "自訂主題"]
    )
    
    difficulty = st.selectbox(
        "選擇難度模式",
        ["標準模式 (100分, 最多2次提示)", "輕鬆模式 (100分, 無限提示)", "挑戰模式 (100分, 限10問, 無提示)"]
    )
    
    st.divider()
    if st.button("🔄 重新開始新遊戲", type="primary", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.divider()
    st.header("🏆 全球排行榜")
    top_scores = get_leaderboard(5)
    if top_scores:
        for idx, (p_name, p_score, p_cat, p_diff, p_time) in enumerate(top_scores, 1):
            st.markdown(f"**{idx}. {p_name}** — 🌟 **{p_score}分**\n> *{p_cat} | {p_diff.split(' ')[0]}*")
    else:
        st.info("尚無排行榜紀錄，快來挑戰第一名！")

# Handle API Key
if api_key_input:
    os.environ["GEMINI_API_KEY"] = api_key_input

# Initialize Session States
if "game_won" not in st.session_state:
    st.session_state.game_won = False
if "score_saved" not in st.session_state:
    st.session_state.score_saved = False
if "final_score" not in st.session_state:
    st.session_state.final_score = 85  # Default estimation or extracted score

# Initialize Chat Session
if "chat_session" not in st.session_state or "messages" not in st.session_state:
    if not os.environ.get("GEMINI_API_KEY"):
        st.warning("⚠️ 請先在側邊欄輸入您的 Gemini API Key 才能開始遊戲！")
        st.stop()
        
    try:
        client = genai.Client()
        
        system_instruction = f"""
        你是一個專門帶領「頭上文字猜猜樂」（Heads Up! / 猜猜我是誰）互動遊戲的主持人兼問答機器人。
        【遊戲設定】
        - 主題類別：{category}
        - 難度模式：{difficulty}
        【任務規範】
        1. 在心裡隨機選定一個符合上述主題的祕密詞彙（絕對不要一開始就洩漏答案）。
        2. 玩家會透過向你提問來推敲答案。
        3. 你的回答必須明確給出判定：「是 (Yes)」、「不是 (No)」或「不一定 / 很難說 (Depends)」，並可附帶一句簡短的客觀事實。
        4. 每輪回答後，請在結尾顯示當前狀態（包含提問次數、剩餘提示、預估得分數字，例如：【得分：85分】）。
        5. 當玩家猜中答案時，熱烈祝賀並明確給出最終結算得分。
        """
        
        chat = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            )
        )
        st.session_state.chat_session = chat
        
        initial_response = chat.send_message("遊戲正式開始！請扮演主持人，在心中選定謎底，向玩家打招呼並說明遊戲開始，請玩家進行第一次提問。")
        st.session_state.messages = [{"role": "assistant", "content": initial_response.text}]
        
    except Exception as e:
        st.error(f"❌ 初始化遊戲失敗: {e}")
        st.stop()

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Check if game was won in previous turns
if st.session_state.game_won and not st.session_state.score_saved:
    st.success("🎉 恭喜你成功猜中答案！")
    with st.form("score_form"):
        st.subheader("📝 登記你的分數到排行榜")
        player_name = st.text_input("輸入你的玩家名稱：", value="玩家 1")
        submitted = st.form_submit_button("儲存分數")
        if submitted:
            save_score(player_name, st.session_state.final_score, category, difficulty)
            st.session_state.score_saved = True
            st.success("✨ 分數已成功儲存至排行榜！請點擊側邊欄「重新開始新遊戲」再來一局。")
            st.rerun()

# User Input Handling (Disabled if game is won until reset)
if not st.session_state.game_won:
    if user_input := st.chat_input("請輸入你的問題（例如：我是人類嗎？）或輸入「提示」..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
            
        with st.chat_message("assistant"):
            with st.spinner("🤖 主持人思考中..."):
                try:
                    response = st.session_state.chat_session.send_message(user_input)
                    bot_reply = response.text
                    st.markdown(bot_reply)
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    
                    # Detect win condition keywords
                    if any(kw in bot_reply for kw in ["恭喜", "勝利", "猜中了", "答對了"]):
                        st.session_state.game_won = True
                        st.rerun()
                except Exception as e:
                    error_msg = f"❌ 發生錯誤: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})