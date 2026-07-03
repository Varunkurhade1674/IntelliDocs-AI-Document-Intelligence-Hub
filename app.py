import os
import sqlite3
import json
import uuid
import tempfile
import hashlib
import time
import socket
import streamlit as st

# Force IPv4 to avoid getaddrinfo failures on Windows with IPv6
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0:
        family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo
import pandas as pd
from dotenv import load_dotenv
from pypdf import PdfReader
import docx2txt
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False

load_dotenv()

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
DB_FILE = "chats.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS threads (
        id TEXT PRIMARY KEY, title TEXT, username TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT,
        role TEXT, content TEXT, sources TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE)""")
    c.execute("PRAGMA table_info(threads)")
    cols = [col[1] for col in c.fetchall()]
    if "username" not in cols:
        try: c.execute("ALTER TABLE threads ADD COLUMN username TEXT")
        except: pass
    conn.commit(); conn.close()

def hash_password(p):
    return hashlib.sha256(("intellidocs_secure_salt_989!" + p).encode()).hexdigest()

def register_user(u, p):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username=?", (u,))
    if c.fetchone(): conn.close(); return False
    c.execute("INSERT INTO users (username,password_hash) VALUES (?,?)", (u, hash_password(p)))
    conn.commit(); conn.close(); return True

def verify_user(u, p):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username=? AND password_hash=?", (u, hash_password(p)))
    r = c.fetchone(); conn.close(); return r is not None

def user_exists(u):
    """Check if a username exists in the DB."""
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username=?", (u,))
    r = c.fetchone(); conn.close(); return r is not None

def reset_password(u, new_p):
    """Directly update a user's password (local-only reset — no email needed)."""
    if not user_exists(u): return False
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(new_p), u))
    conn.commit(); conn.close(); return True

def get_threads(username):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT id,title,timestamp FROM threads WHERE username=? ORDER BY timestamp DESC", (username,))
    r = c.fetchall(); conn.close(); return r

def create_thread(tid, title, username):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT INTO threads (id,title,username) VALUES (?,?,?)", (tid, title, username))
    conn.commit(); conn.close()

def delete_thread(tid):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("DELETE FROM threads WHERE id=?", (tid,))
    c.execute("DELETE FROM messages WHERE thread_id=?", (tid,))
    conn.commit(); conn.close()

def save_message(tid, role, content, sources=None):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT INTO messages (thread_id,role,content,sources) VALUES (?,?,?,?)",
              (tid, role, content, json.dumps(sources) if sources else None))
    c.execute("UPDATE threads SET timestamp=CURRENT_TIMESTAMP WHERE id=?", (tid,))
    conn.commit(); conn.close()

def get_messages(tid):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT role,content,sources FROM messages WHERE thread_id=? ORDER BY id ASC", (tid,))
    rows = c.fetchall(); conn.close()
    return [{"role": r[0], "content": r[1], **({"sources": json.loads(r[2])} if r[2] else {})} for r in rows]

init_db()

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="IntelliDocs AI",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# MASTER CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap');

/* ── FORCE DARK MODE ── */
html, body { background: #0D0F1A !important; }
.stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
    background: #0D0F1A !important;
    font-family: 'Inter', sans-serif !important;
    --primary-color: #6366F1 !important;
}

/* ── HIDE STREAMLIT CHROME ── */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton { display: none !important; }

/* ── BLOCK CONTAINER ── */
[data-testid="stMainBlockContainer"] {
    padding: 0 !important;
    max-width: 100% !important;
}
/* ── Scoped Layout Gaps ── */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 8px !important;
}

/* ══════════════════════════════════════════
   AUTH CARD
══════════════════════════════════════════ */
.auth-wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 16px;
    background: #0D0F1A;
}

/* Style the Streamlit form AS the card */
[data-testid="stForm"] {
    background: #141828 !important;
    border-radius: 22px !important;
    padding: 40px 44px 36px !important;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2),
                0 20px 48px -12px rgba(0,0,0,0.4) !important;
    border: 1px solid #1E2340 !important;
    animation: fadeUp .45s cubic-bezier(.22,1,.36,1) both !important;
}

@keyframes fadeUp {
    from { opacity:0; transform:translateY(18px) scale(.98); }
    to   { opacity:1; transform:translateY(0)   scale(1);   }
}

/* ══════════════════════════════
   TEXT INPUT — comprehensive fix
══════════════════════════════ */

/* Label */
.stTextInput > label,
[data-testid="stTextInput"] > label {
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #8892A4 !important;
    text-transform: uppercase !important;
    letter-spacing: .8px !important;
    margin-bottom: 6px !important;
    display: block !important;
    font-family: 'Inter', sans-serif !important;
}

/* ── Wrapper (baseweb) ── */
[data-baseweb="input"],
[data-baseweb="base-input"],
.stTextInput [data-baseweb="input"],
.stTextInput [data-baseweb="base-input"] {
    background: #111427 !important;
    border: 1.5px solid #1E2340 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 2px rgba(0,0,0,.1) !important;
    transition: border-color .18s, box-shadow .18s !important;
    min-height: 46px !important;
}

/* Focus state on wrapper */
[data-baseweb="input"]:focus-within,
[data-baseweb="base-input"]:focus-within,
.stTextInput [data-baseweb="input"]:focus-within {
    border-color: #6366F1 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,.2), 0 1px 2px rgba(0,0,0,.1) !important;
    background: #111427 !important;
}

/* ── The actual <input> element ── */
[data-baseweb="input"] input,
[data-baseweb="base-input"] input,
.stTextInput input,
input[type="text"],
input[type="password"],
input[type="email"],
input[type="search"] {
    background: transparent !important;
    background-color: transparent !important;
    color: #F1F5F9 !important;
    -webkit-text-fill-color: #F1F5F9 !important;
    font-size: 14.5px !important;
    font-family: 'Inter', sans-serif !important;
    padding: 12px 14px !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    caret-color: #6366F1 !important;
    line-height: 1.4 !important;
}

/* Placeholder */
[data-baseweb="input"] input::placeholder,
.stTextInput input::placeholder,
input::placeholder {
    color: #4B5563 !important;
    -webkit-text-fill-color: #4B5563 !important;
    opacity: 1 !important;
}

/* ── Webkit autofill — prevent yellow bg ── */
input:-webkit-autofill,
input:-webkit-autofill:hover,
input:-webkit-autofill:focus {
    -webkit-box-shadow: 0 0 0 100px #111427 inset !important;
    -webkit-text-fill-color: #F1F5F9 !important;
    border-radius: 10px !important;
}

/* ── Password eye toggle button ── */
[data-baseweb="input"] button,
[data-baseweb="base-input"] button {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #8892A4 !important;
    padding: 0 12px !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
}
[data-baseweb="input"] button:hover,
[data-baseweb="base-input"] button:hover {
    color: #6366F1 !important;
    background: transparent !important;
}
[data-baseweb="input"] button svg,
[data-baseweb="base-input"] button svg {
    fill: currentColor !important;
    width: 18px !important;
    height: 18px !important;
}


/* ── st.tabs() as Segmented Control ── */
/* Hide the underline bar */
[data-baseweb="tab-border"]       { display: none !important; }
[data-baseweb="tab-highlight"]    { display: none !important; }

/* Tab list = pill strip */
[data-baseweb="tab-list"] {
    background: #0D0F1A !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    border-bottom: none !important;
    width: 100% !important;
    margin-bottom: 20px !important;
}

/* Each tab */
[data-baseweb="tab"] {
    flex: 1 !important;
    border-radius: 9px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    color: #8892A4 !important;
    padding: 9px 12px !important;
    border: none !important;
    background: transparent !important;
    transition: all .18s ease !important;
    justify-content: center !important;
    white-space: nowrap !important;
    outline: none !important;
    box-shadow: none !important;
    font-family: 'Inter', sans-serif !important;
}
[data-baseweb="tab"]:hover {
    color: #F1F5F9 !important;
    background: rgba(255,255,255,.05) !important;
}

/* Active tab = white pill */
[data-baseweb="tab"][aria-selected="true"] {
    background: #141828 !important;
    color: #F1F5F9 !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 5px rgba(0,0,0,.3), 0 0 0 .5px rgba(255,255,255,.05) !important;
}

/* Tab panel = no extra padding */
[data-testid="stTabsTabPanel"] {
    padding-top: 4px !important;
}

/* Forms inside tabs: transparent (card is the form container) */
[data-testid="stTabs"] [data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 8px 0 0 !important;
}


/* ── Submit button ── */
[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    font-size: 14.5px !important;
    font-weight: 600 !important;
    padding: 13px 28px !important;
    font-family: 'Inter', sans-serif !important;
    letter-spacing: .2px !important;
    box-shadow: 0 4px 14px rgba(99,102,241,.30) !important;
    transition: all .2s !important;
    width: 100% !important;
    margin-top: 6px !important;
}
[data-testid="stFormSubmitButton"] > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 24px rgba(99,102,241,.42) !important;
}
[data-testid="stFormSubmitButton"] > button:active {
    transform: translateY(0) !important;
}

/* ── Alerts (inside form) ── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    font-size: 13.5px !important;
    font-family: 'Inter', sans-serif !important;
}

/* ══════════════════════════════════════════
   SIDEBAR
══════════════════════════════════════════ */
section[data-testid="stSidebar"] {
    background: #111427 !important;
    border-right: 1px solid #1E2340 !important;
    box-shadow: 1px 0 0 #1E2340 !important;
    width: 268px !important;
    min-width: 268px !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
}
[data-testid="stSidebarContent"] {
    padding: 0 16px !important;
}
[data-testid="stSidebarUserContent"] {
    padding: 20px 0 !important;
}

/* Global premium labels */
label, 
label p, 
[data-testid="stWidgetLabel"] p {
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: .8px !important;
    color: #8892A4 !important; 
    margin-bottom: 6px !important;
    font-family: 'Inter', sans-serif !important;
}

/* Sidebar buttons */
section[data-testid="stSidebar"] .stButton > button {
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    height: 38px !important;
    transition: all .15s !important;
    border: 1px solid #1E2340 !important;
    background: #141828 !important;
    color: #F1F5F9 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 0 14px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #1E2340 !important;
    border-color: #313753 !important;
    color: #FFFFFF !important;
}

/* Active chat thread styling */
section[data-testid="stSidebar"] .stButton > button.active-thread {
    background: #1E2340 !important;
    border-left: 3px solid #6366F1 !important;
    color: #FFFFFF !important;
}

/* Sidebar log out button custom styling */
.st-key-btn_logout button {
    background: rgba(239, 68, 68, 0.1) !important;
    border: 1px solid rgba(239, 68, 68, 0.2) !important;
    color: #F87171 !important;
    justify-content: center !important;
    font-weight: 600 !important;
    text-align: center !important;
}
.st-key-btn_logout button:hover {
    background: #EF4444 !important;
    border-color: #EF4444 !important;
    color: #FFFFFF !important;
}

/* Global selectbox overrides */
[data-baseweb="select"] {
    border-radius: 10px !important;
    border: 1.5px solid #1E2340 !important;
    background-color: #111427 !important;
    background: #111427 !important;
    font-size: 13.5px !important;
    transition: all 0.15s ease !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-baseweb="select"] > div {
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    background-color: transparent !important;
    background: transparent !important;
}
[data-baseweb="select"]:focus-within {
    border-color: #6366F1 !important;
    background-color: #141828 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,.2) !important;
}
[data-baseweb="select"] div {
    background-color: transparent !important;
    background: transparent !important;
    color: #F1F5F9 !important;
}
[data-baseweb="select"] [role="button"],
[data-baseweb="select"] [aria-selected="true"] {
    color: #F1F5F9 !important;
}
[data-baseweb="select"] svg {
    color: #8892A4 !important;
    fill: currentColor !important;
}

/* Global file uploader overrides */
[data-testid="stFileUploadDropzone"] {
    background-color: #111427 !important;
    background: #111427 !important;
    border: 1.5px dashed #313753 !important;
    border-radius: 10px !important;
    padding: 16px !important;
    transition: all 0.15s ease !important;
}
[data-testid="stFileUploadDropzone"]:hover {
    border-color: #6366F1 !important;
    background-color: rgba(99,102,241,.05) !important;
    background: rgba(99,102,241,.05) !important;
}
[data-testid="stFileUploadDropzone"] div {
    background-color: transparent !important;
    background: transparent !important;
}
[data-testid="stFileUploadDropzone"] p,
[data-testid="stFileUploadDropzone"] span,
[data-testid="stFileUploadDropzone"] label {
    font-size: 12.5px !important;
    color: #8892A4 !important;
    font-weight: 500 !important;
}
[data-testid="stFileUploadDropzone"] button,
[data-testid="stFileUploadDropzone"] button div {
    background-color: #1E2340 !important;
    background: #1E2340 !important;
    border: 1px solid #313753 !important;
    color: #F1F5F9 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
}
[data-testid="stFileUploadDropzone"] button:hover {
    background-color: #313753 !important;
    background: #313753 !important;
    border-color: #6366F1 !important;
    color: #FFFFFF !important;
}

/* Global slider overrides */
div[data-testid="stSlider"] [role="slider"] {
    background-color: #6366F1 !important;
    border-color: #6366F1 !important;
}
div[data-testid="stSlider"] [data-baseweb="slider"] > div {
    background: #313753 !important;
}
div[data-testid="stSlider"] [data-baseweb="slider"] > div > div {
    background: #6366F1 !important;
}
div[data-testid="stSlider"] div[data-testid="stWidgetLabel"] span {
    color: #6366F1 !important;
    font-weight: 600 !important;
}
[data-testid="stSlider"] div {
    color: #8892A4 !important;
}

/* Streamlit Alert text colors */
[data-testid="stAlert"] div {
    color: #F1F5F9 !important;
}
[data-testid="stAlert"] svg {
    color: #F59E0B !important;
    fill: currentColor !important;
}

/* ══════════════════════════════════════════
   TOPBAR
══════════════════════════════════════════ */
.topbar {
    position: sticky;
    top: 0;
    z-index: 100;
    height: 58px;
    background: rgba(20, 24, 40, 0.8);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid #1E2340;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 28px;
    box-shadow: 0 1px 3px rgba(0,0,0,.2);
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.topbar-icon {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px;
}
.topbar-title { font-size: 15px; font-weight: 700; color: #FFFFFF; letter-spacing: -.2px; }
.topbar-sub   { font-size: 11.5px; color: #8892A4; margin-top: 1px; }
.topbar-pill  {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 20px; padding: 4px 11px;
    font-size: 12px; color: #818CF8; font-weight: 500;
}
.topbar-pill-dot {
    width: 6px; height: 6px; background: #6366F1; border-radius: 50%;
    animation: blink 2s ease-in-out infinite;
    display: inline-block;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.4} }

/* ══════════════════════════════════════════
   CHAT AREA
══════════════════════════════════════════ */
.chat-outer {
    max-width: 740px;
    margin: 0 auto;
    padding: 28px 24px 8px;
}

/* Native stChatMessage overrides */
[data-testid="stChatMessage"] {
    background: transparent !important;
    padding: 2px 0 !important;
    max-width: 740px !important;
    margin: 0 auto !important;
    animation: msgPop .32s cubic-bezier(.34,1.56,.64,1) both !important;
}
@keyframes msgPop {
    from { opacity:0; transform:translateY(14px) scale(.97); }
    to   { opacity:1; transform:translateY(0)    scale(1);   }
}

/* ── ALL chat message content: ensure text is always visible ── */
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"] .stMarkdown,
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] span {
    color: #F1F5F9 !important;
    -webkit-text-fill-color: #F1F5F9 !important;
}

/* AI bubble — old Streamlit (data-author) + new Streamlit (nth-child/aria) */
[data-testid="stChatMessage"][data-author="assistant"] [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:not(:has([data-testid="chatAvatarIcon-user"])) [data-testid="stChatMessageContent"] {
    background: #141828 !important;
    border: 1px solid #1E2340 !important;
    border-radius: 4px 18px 18px 18px !important;
    padding: 14px 18px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,.2) !important;
    color: #F1F5F9 !important;
    font-size: 14.5px !important;
    line-height: 1.68 !important;
    max-width: 78% !important;
}
[data-testid="stChatMessage"][data-author="assistant"] [data-testid="stChatMessageContent"] p,
[data-testid="stChatMessage"][data-author="assistant"] [data-testid="stChatMessageContent"] li,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] p,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] li {
    color: #F1F5F9 !important;
    -webkit-text-fill-color: #F1F5F9 !important;
}

/* User bubble — old + new Streamlit */
[data-testid="stChatMessage"][data-author="user"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    flex-direction: row-reverse !important;
}
[data-testid="stChatMessage"][data-author="user"] [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
    background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%) !important;
    border: none !important;
    border-radius: 18px 4px 18px 18px !important;
    padding: 14px 18px !important;
    box-shadow: 0 4px 14px rgba(99,102,241,.28) !important;
    color: #FFFFFF !important;
    font-size: 14.5px !important;
    line-height: 1.65 !important;
    max-width: 78% !important;
    margin-left: auto !important;
}
[data-testid="stChatMessage"][data-author="user"] [data-testid="stChatMessageContent"] p,
[data-testid="stChatMessage"][data-author="user"] [data-testid="stChatMessageContent"] li,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] p,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] li {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}

/* Avatars */
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {
    background: linear-gradient(135deg, #6366F1, #8B5CF6) !important;
    border-radius: 50% !important;
    border: none !important;
}
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] {
    background: #313753 !important;
    border-radius: 50% !important;
    border: none !important;
}

/* ── Source expander ── */
[data-testid="stExpander"] {
    background: #111427 !important;
    border: 1px solid #1E2340 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    background-color: #111427 !important;
    color: #F1F5F9 !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary div,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary svg {
    color: #F1F5F9 !important;
    fill: currentColor !important;
}
[data-testid="stExpander"] [data-testid="stVerticalBlock"] {
    background-color: #141828 !important;
    padding: 12px 14px !important;
}

/* ── Chat input ── */
[data-testid="stChatInput"] {
    background: #141828 !important;
    border: 1.5px solid #1E2340 !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,.3) !important;
    max-width: 740px !important;
    margin: 0 auto !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14.5px !important;
    transition: border-color .18s, box-shadow .18s !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #6366F1 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,.2), 0 4px 12px rgba(0,0,0,.3) !important;
}
[data-testid="stChatInput"] > div {
    background-color: transparent !important;
    border: none !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #F1F5F9 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14.5px !important;
}

/* ── Input wrapper centering ── */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
.stBottom,
.stBottom > div {
    background: #0D0F1A !important;
    background-color: #0D0F1A !important;
    border-top: 1px solid #1E2340 !important;
    padding: 16px 24px 20px !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] p { color: #6366F1 !important; font-size: 13px !important; }

/* ── Download button ── */
.stDownloadButton > button {
    background: rgba(99,102,241,.1) !important;
    border: 1px solid rgba(99,102,241,.3) !important;
    color: #818CF8 !important;
    border-radius: 9px !important;
    font-size: 12.5px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    font-family: 'Inter', sans-serif !important;
    transition: all .15s !important;
}
.stDownloadButton > button:hover {
    background: #6366F1 !important;
    border-color: #6366F1 !important;
    color: white !important;
}

/* ── Toast ── */
[data-testid="stToast"] {
    background: #141828 !important;
    border: 1px solid #1E2340 !important;
    color: #F1F5F9 !important;
    border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13.5px !important;
}

/* ── Empty state ── */
.empty-wrap {
    text-align: center;
    max-width: 480px;
    margin: 0 auto;
    padding: 56px 20px 20px;
    animation: fadeUp .4s ease both;
}
.empty-icon  { font-size: 44px; margin-bottom: 18px; display: block; }
.empty-h     { font-size: 20px; font-weight: 700; color: #F1F5F9; letter-spacing: -.3px; margin-bottom: 8px; }
.empty-p     { font-size: 14px; color: #8892A4; line-height: 1.6; margin-bottom: 28px; }
.sg-grid     { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 400px; margin: 0 auto; }
.sg-card     {
    background: #141828; border: 1px solid #1E2340; border-radius: 14px;
    padding: 16px; text-align: left; cursor: pointer;
    transition: all .18s; font-size: 12.5px; color: #E2E8F0; line-height: 1.45;
}
.sg-card:hover { border-color: #6366F1; background: rgba(99,102,241,.05); color: #818CF8; }
.sg-icon { font-size: 20px; margin-bottom: 8px; display: block; }

/* ── Sidebar section label ── */
.sb-section {
    font-size: 10.5px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .7px; color: #8892A4; padding: 14px 0 6px;
}
.sb-divider { border-top: 1px solid #1E2340; margin: 10px 0; }
.sb-stat-card {
    background: #111427; border: 1px solid #1E2340; border-radius: 12px;
    padding: 12px 14px; margin-bottom: 10px;
}
.sb-stat-row  { display:flex; justify-content:space-between; margin-bottom:6px; }
.sb-stat-row:last-child { margin-bottom:0; }
.sb-stat-lbl  { font-size: 11.5px; color: #8892A4; }
.sb-stat-val  { font-size: 12.5px; font-weight: 600; color: #F1F5F9; }
.sb-status    { display:flex; align-items:center; gap:7px; font-size:12.5px; padding:4px 0; }
.sb-dot-ok    { width:7px;height:7px;border-radius:50%;background:#10B981;display:inline-block; }
.sb-dot-err   { width:7px;height:7px;border-radius:50%;background:#EF4444;display:inline-block; }
.sb-header    {
    padding: 18px 14px 14px;
    border-bottom: 1px solid #1E2340;
    display: flex; align-items: center; gap: 10px;
}
.sb-header-icon {
    width: 34px; height: 34px;
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    border-radius: 10px; display:flex; align-items:center;
    justify-content:center; font-size:17px; flex-shrink:0;
}
.sb-header-name { font-size:15px; font-weight:700; color:#F1F5F9; letter-spacing:-.2px; }
.sb-header-sub  { font-size:11px; color:#8892A4; margin-top:1px; }

/* ── Right Workspace Panel ── */
.st-key-workspace_panel {
    background: #141828 !important;
    border-radius: 16px !important;
    border: 1px solid #1E2340 !important;
    padding: 22px 24px 24px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2) !important;
}

/* Tabs inside workspace panel */
.st-key-workspace_panel [data-baseweb="tab-list"] {
    background: #0D0F1A !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 4px !important;
    border-bottom: none !important;
    width: 100% !important;
    margin-bottom: 16px !important;
}
.st-key-workspace_panel [data-baseweb="tab-border"],
.st-key-workspace_panel [data-baseweb="tab-highlight"] {
    display: none !important;
}
.st-key-workspace_panel [data-baseweb="tab"] {
    flex: 1 !important;
    border-radius: 7px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #8892A4 !important;
    padding: 7px 10px !important;
    border: none !important;
    background: transparent !important;
    transition: all .15s ease !important;
    justify-content: center !important;
    white-space: nowrap !important;
    font-family: 'Inter', sans-serif !important;
}
.st-key-workspace_panel [data-baseweb="tab"]:hover {
    color: #F1F5F9 !important;
    background: rgba(255,255,255,.05) !important;
}
.st-key-workspace_panel [data-baseweb="tab"][aria-selected="true"] {
    background: #1E2340 !important;
    color: #F1F5F9 !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.3) !important;
}
.st-key-workspace_panel [data-testid="stTabsTabPanel"] {
    padding-top: 0 !important;
}

/* Baseweb popovers & dropdown option lists */
[data-baseweb="popover"],
[data-baseweb="menu"],
div[role="listbox"],
ul[role="listbox"],
li[role="option"] {
    background-color: #141828 !important;
    background: #141828 !important;
    color: #F1F5F9 !important;
}
li[role="option"]:hover,
li[role="option"][aria-selected="true"] {
    background-color: #1E2340 !important;
    color: #818CF8 !important;
}

/* ── Sidebar Footer Pinning ── */
[data-testid="stSidebarContent"] > div:first-child {
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
    min-height: calc(100vh - 40px) !important;
}
.st-key-sidebar_footer {
    margin-top: auto !important;
    background: #111427 !important;
    padding-top: 16px !important;
    border-top: 1px solid #1E2340 !important;
    padding-bottom: 8px !important;
}

/* Style suggestion buttons to look like premium cards */
.st-key-suggestion_grid {
    max-width: 480px;
    margin: -10px auto 28px !important;
}
.st-key-suggestion_grid .stButton > button {
    background: #141828 !important;
    border: 1px solid #1E2340 !important;
    border-radius: 14px !important;
    padding: 16px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    cursor: pointer !important;
    transition: all .18s !important;
    font-size: 13px !important;
    color: #E2E8F0 !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
    white-space: normal !important;
    word-break: break-word !important;
    height: auto !important;
    min-height: 68px !important;
}
.st-key-suggestion_grid .stButton > button:hover {
    border-color: #6366F1 !important;
    background: rgba(99,102,241,.05) !important;
    color: #818CF8 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(99,102,241,0.15) !important;
}
.st-key-suggestion_grid .stButton > button p {
    margin: 0 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: inherit !important;
    text-transform: none !important;
    letter-spacing: normal !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def ocr_pdf_with_groq(file):
    """Use Groq Vision to OCR a scanned/image-based PDF via pymupdf rendering."""
    try:
        import fitz  # pymupdf
        import base64
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage
    except ImportError:
        return []
    
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return []

    docs = []
    file_bytes = file.getvalue()
    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", groq_api_key=key, temperature=0.0)
        total = len(pdf_doc)
        progress = st.progress(0, text=f"🔍 OCR scanning {total} page(s) with Groq Vision…")
        for page_num in range(total):
            progress.progress((page_num) / total,
                              text=f"🔍 OCR page {page_num+1}/{total} of **{file.name}**…")
            page = pdf_doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)   # 2× zoom ≈ 144 DPI – good quality
            pix = page.get_pixmap(matrix=mat)
            img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            
            for attempt in range(3):
                try:
                    msg = HumanMessage(
                        content=[
                            {"type": "text", "text": "Extract ALL text from this document image exactly as it appears. Preserve paragraphs, tables, bullet points and numbers. Return only the extracted text — no commentary, no markdown fencing."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                        ]
                    )
                    resp = llm.invoke([msg])
                    text = resp.content.strip()
                    if text:
                        docs.append(Document(
                            page_content=text,
                            metadata={"source": file.name, "page": page_num + 1, "method": "groq-ocr"}
                        ))
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        st.warning(f"Groq OCR failed on page {page_num+1}: {e}")
        progress.progress(1.0, text=f"✅ OCR complete — {len(docs)} page(s) extracted from **{file.name}**")
        pdf_doc.close()
    except Exception as e:
        st.error(f"Groq OCR pipeline error: {e}")
    return docs
def ocr_pdf_with_gemini(file):
    """Use Gemini Vision to OCR a scanned/image-based PDF via pymupdf rendering."""
    try:
        import fitz  # pymupdf
        from google import genai as gai
        from google.genai import types as gai_types
    except ImportError:
        return []

    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        return []

    docs = []
    file_bytes = file.getvalue()
    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        client = gai.Client(api_key=key)
        total = len(pdf_doc)
        progress = st.progress(0, text=f"🔍 OCR scanning {total} page(s) with Gemini Vision…")
        for page_num in range(total):
            progress.progress((page_num) / total,
                              text=f"🔍 OCR page {page_num+1}/{total} of **{file.name}**…")
            page = pdf_doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)   # 2× zoom ≈ 144 DPI – good quality
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            for attempt in range(3):
                try:
                    resp = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[
                            gai_types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                            ("Extract ALL text from this document image exactly as it appears. "
                             "Preserve paragraphs, tables, bullet points and numbers. "
                             "Return only the extracted text — no commentary, no markdown fencing.")
                        ]
                    )
                    text = resp.text.strip() if resp.text else ""
                    if text:
                        docs.append(Document(
                            page_content=text,
                            metadata={"source": file.name, "page": page_num + 1, "method": "gemini-ocr"}
                        ))
                    break
                except Exception as e:
                    err_s = str(e)
                    if "API_KEY_INVALID" in err_s or "expired" in err_s.lower() or "API key expired" in err_s:
                        st.warning("⚠️ **Gemini API key expired.** OCR is unavailable for scanned documents. Please renew your key to enable image text extraction.")
                        return docs  # Stop OCR completely
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        st.warning(f"OCR failed on page {page_num+1}: {e}")
        progress.progress(1.0, text=f"✅ OCR complete — {len(docs)} page(s) extracted from **{file.name}**")
        pdf_doc.close()
    except Exception as e:
        err_str = str(e)
        if "API_KEY_INVALID" in err_str or "expired" in err_str.lower() or "API key expired" in err_str:
            st.error("🔑 **Gemini API key has expired.** OCR scanning for image-based PDFs is unavailable.")
        else:
            st.error(f"OCR pipeline error: {e}")
    return docs

def extract_text_from_file(file):
    docs = []; ext = os.path.splitext(file.name)[1].lower()
    try:
        if ext == ".pdf":
            reader = PdfReader(file)
            for i, page in enumerate(reader.pages):
                t = None
                # Try layout-aware extraction first (better for complex PDFs)
                try:
                    t = page.extract_text(extraction_mode="layout")
                except Exception:
                    pass
                # Fallback to standard extraction
                if not t or not t.strip():
                    t = page.extract_text()
                if t and t.strip():
                    docs.append(Document(page_content=t, metadata={"source": file.name, "page": i+1}))
            # If no embedded text found → auto OCR with Vision
            if not docs:
                st.info(f"📷 **{file.name}** is a scanned PDF — running Vision OCR automatically…")
                if os.getenv("GROQ_API_KEY"):
                    docs = ocr_pdf_with_groq(file)
                if not docs and (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
                    docs = ocr_pdf_with_gemini(file)
                if not docs:
                    st.error(f"❌ Could not extract any text from **{file.name}** even with OCR. Make sure you have a valid Groq or Gemini API key.")
        elif ext == ".docx":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(file.getvalue()); path = tmp.name
            t = docx2txt.process(path); os.unlink(path)
            if t and t.strip(): docs.append(Document(page_content=t, metadata={"source": file.name, "page": 1}))
        elif ext == ".txt":
            t = file.getvalue().decode("utf-8", errors="ignore")
            if t and t.strip(): docs.append(Document(page_content=t, metadata={"source": file.name, "page": 1}))
        elif ext == ".csv":
            t = pd.read_csv(file).to_markdown(index=False)
            if t and t.strip(): docs.append(Document(page_content=t, metadata={"source": file.name, "page": 1}))
    except Exception as e:
        st.error(f"Error parsing {file.name}: {e}")
    return docs

def build_vectorstore(docs, provider):
    if not docs: return None
    chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(docs)
    if provider == "Google Gemini":
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not key:
            st.error("❌ Missing GEMINI_API_KEY in .env — please switch to **Groq + HuggingFace (Free)** above (no key needed!)")
            return None
        emb = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=key)
    elif provider == "Groq + HuggingFace (Free)":
        if not _HF_AVAILABLE:
            st.error("langchain-huggingface not installed. Run: pip install langchain-huggingface sentence-transformers")
            return None
        with st.spinner("Loading HuggingFace embedding model (first run may take a moment)…"):
            emb = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True}
            )
    else:
        key = os.getenv("OPENAI_API_KEY")
        if not key: st.error("Missing OPENAI_API_KEY in .env"); return None
        emb = OpenAIEmbeddings(api_key=key)
    # Retry up to 3 times on transient network errors
    for attempt in range(3):
        try:
            vs = FAISS.from_documents(chunks, emb)
            return vs, len(chunks)
        except Exception as e:
            err_str = str(e)
            # Detect expired / invalid Gemini API key specifically
            if "API_KEY_INVALID" in err_str or "expired" in err_str.lower() or "API key expired" in err_str:
                st.error(
                    "🔑 **Your Gemini API key has expired or is invalid.**\n\n"
                    "👉 Switch the **Embedding Model** above to **Groq + HuggingFace (Free)** "
                    "— it works with no API key and pairs perfectly with Groq!"
                )
                return None
            elif attempt < 2 and ("getaddrinfo" in err_str or "timeout" in err_str.lower() or "connection" in err_str.lower()):
                st.toast(f"Network hiccup, retrying… ({attempt+1}/3)")
                time.sleep(2)
            else:
                st.error(f"Embedding failed: {e}")
                return None

# Gemini model fallback chain — gemini-2.5-flash first (most reliable)
GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]

def get_llm(provider, model, temp):
    if provider == "OpenAI":
        return ChatOpenAI(model=model, temperature=temp, api_key=os.getenv("OPENAI_API_KEY"))
    if provider == "Google Gemini":
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(model=model, temperature=temp, google_api_key=key)
    return ChatGroq(model=model, temperature=temp, groq_api_key=os.getenv("GROQ_API_KEY"))

def invoke_llm_with_fallback(provider, model, temp, msgs):
    """Try the selected model, fall back through alternatives on 429 rate-limit."""
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    if provider != "Google Gemini":
        llm = get_llm(provider, model, temp)
        return llm.stream(msgs), model
    
    # Build fallback list: requested model first, then others
    fallbacks = [model] + [m for m in GEMINI_FALLBACK_MODELS if m != model]
    last_err = None
    for try_model in fallbacks:
        try:
            llm = ChatGoogleGenerativeAI(model=try_model, temperature=temp, google_api_key=key)
            # Test with a tiny ping first to fail fast on rate limits
            stream = llm.stream(msgs)
            return stream, try_model
        except Exception as e:
            last_err = e
            err_s = str(e)
            if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s or "quota" in err_s.lower():
                continue   # try next model
            raise          # non-rate-limit error → re-raise immediately
    raise last_err

def export_chat():
    md = f"# IntelliDocs AI — Chat Export\n*{pd.Timestamp.now():%Y-%m-%d %H:%M}*\n\n---\n\n"
    for m in st.session_state.chat_history:
        label = "👤 You" if m["role"] == "user" else "🤖 IntelliDocs AI"
        md += f"### {label}\n{m['content']}\n\n"
        if m.get("sources"):
            md += "**Sources:** " + ", ".join(f"`{s['file']}` p{s['page']}" for s in m["sources"]) + "\n\n"
        md += "---\n\n"
    return md

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
DEFAULTS = dict(authenticated=False, username=None, chat_history=[],
                vector_store=None, document_stats={"pages":0,"chunks":0,"files":[]},
                current_thread_id=None, show_login_toast=False,
                sel_prov="Groq", sel_model="llama-3.3-70b-versatile", sld_temp=0.2,
                sel_embed="Groq + HuggingFace (Free)", embed_provider="Groq + HuggingFace (Free)",
                show_reset=False,   # ← forgot-password panel toggle
                auth_mode="login",
                reset_success_msg=None)
for k, v in DEFAULTS.items():
    if k not in st.session_state: st.session_state[k] = v

# ══════════════════════════════════════════════
# AUTH SCREEN
# ══════════════════════════════════════════════
if not st.session_state.authenticated:

    # ── Auth-scoped CSS ──
    st.markdown("""
    <style>
    /* Card limit and centering */
    section.main [data-testid="stForm"] {
        max-width: 440px !important;
        margin: 0 auto !important;
    }
    
    /* Navigation buttons under the auth card */
    .st-key-go_reset_btn button,
    .st-key-go_signup_btn button,
    .st-key-back_signin_btn button {
        background: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        color: #4B5563 !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
        height: 38px !important;
        font-size: 13.5px !important;
        justify-content: center !important;
        transition: all 0.15s ease !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    }
    .st-key-go_reset_btn button:hover,
    .st-key-go_signup_btn button:hover,
    .st-key-back_signin_btn button:hover {
        background: #F9FAFB !important;
        border-color: #D1D5DB !important;
        color: #111827 !important;
    }
    
    /* Info box inside the card */
    .auth-info-box {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 12px 14px;
        background: #FFFBEB;
        border: 1px solid #FDE68A;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .auth-info-text {
        font-size: 12.5px;
        color: #92400E;
        font-family: 'Inter', sans-serif;
        line-height: 1.5;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Layout: centered column ──
    st.markdown("<div style='height:64px'></div>", unsafe_allow_html=True)
    _, C, _ = st.columns([1, 1.2, 1])
    with C:

        # ════════════════════
        # SIGN IN MODE
        # ════════════════════
        if st.session_state.auth_mode == "login":
            with st.form("signin_form", clear_on_submit=False):
                # Branding Header
                st.markdown("""
                <div style="text-align:center;padding-bottom:12px;margin-bottom:20px">
                    <div style="width:52px;height:52px;background:linear-gradient(135deg,#6366F1,#8B5CF6);
                        border-radius:15px;display:inline-flex;align-items:center;justify-content:center;
                        font-size:24px;box-shadow:0 6px 18px rgba(99,102,241,.28);margin-bottom:13px">📄</div>
                    <div style="font-size:22px;font-weight:800;color:#111827;letter-spacing:-.5px;
                        margin-bottom:5px;font-family:'Inter',sans-serif">IntelliDocs AI</div>
                    <div style="font-size:13px;color:#9CA3AF;font-family:'Inter',sans-serif;
                        margin-bottom:14px">Transform documents into conversations</div>
                    <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap">
                        <span style="background:#EEF2FF;border:1px solid #C7D2FE;color:#4338CA;
                            border-radius:20px;padding:3px 10px;font-size:11px;font-weight:500">📑 PDF &amp; DOCX</span>
                        <span style="background:#EEF2FF;border:1px solid #C7D2FE;color:#4338CA;
                            border-radius:20px;padding:3px 10px;font-size:11px;font-weight:500">🧠 Multi-LLM</span>
                        <span style="background:#EEF2FF;border:1px solid #C7D2FE;color:#4338CA;
                            border-radius:20px;padding:3px 10px;font-size:11px;font-weight:500">⚡ RAG</span>
                        <span style="background:#EEF2FF;border:1px solid #C7D2FE;color:#4338CA;
                            border-radius:20px;padding:3px 10px;font-size:11px;font-weight:500">🔒 Private</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if st.session_state.reset_success_msg:
                    st.success(st.session_state.reset_success_msg)
                    st.session_state.reset_success_msg = None

                u_in = st.text_input("Username", placeholder="Enter your username", key="si_user")
                p_in = st.text_input("Password", type="password", placeholder="••••••••", key="si_pass")
                ok_in = st.form_submit_button("Sign In  →", use_container_width=True)
                
                if ok_in:
                    u, p = u_in.strip(), p_in.strip()
                    if not u or not p:
                        st.error("Please fill in all fields.")
                    elif verify_user(u, p):
                        st.session_state.authenticated    = True
                        st.session_state.username         = u
                        st.session_state.show_login_toast = True
                        st.rerun()
                    else:
                        st.error("Incorrect username or password.")

            st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
            col_l, col_r = st.columns(2)
            with col_l:
                if st.button("Forgot password?", key="go_reset_btn", use_container_width=True):
                    st.session_state.auth_mode = "reset"
                    st.rerun()
            with col_r:
                if st.button("Create Account  ✨", key="go_signup_btn", use_container_width=True):
                    st.session_state.auth_mode = "signup"
                    st.rerun()

        # ════════════════════
        # CREATE ACCOUNT MODE
        # ════════════════════
        elif st.session_state.auth_mode == "signup":
            with st.form("signup_form", clear_on_submit=False):
                st.markdown("""
                <div style="text-align:center;padding-bottom:10px;margin-bottom:20px">
                    <div style="width:44px;height:44px;background:linear-gradient(135deg,#6366F1,#8B5CF6);
                        border-radius:13px;display:inline-flex;align-items:center;justify-content:center;
                        font-size:20px;box-shadow:0 4px 14px rgba(99,102,241,.24);margin-bottom:11px">✨</div>
                    <div style="font-size:19px;font-weight:700;color:#111827;letter-spacing:-.3px;
                        margin-bottom:4px;font-family:'Inter',sans-serif">Create your account</div>
                    <div style="font-size:13px;color:#9CA3AF;font-family:'Inter',sans-serif">
                        Get started with IntelliDocs AI for free</div>
                </div>
                """, unsafe_allow_html=True)

                u_up = st.text_input("Username", placeholder="Choose a username", key="su_user")
                p_up = st.text_input("Password", type="password", placeholder="Min. 6 characters", key="su_pass")
                c_up = st.text_input("Confirm Password", type="password", placeholder="Repeat password", key="su_confirm")
                ok_up = st.form_submit_button("Create Account  →", use_container_width=True)
                
                if ok_up:
                    u, p, cp = u_up.strip(), p_up.strip(), c_up.strip()
                    if not u or not p:
                        st.error("Please fill in all fields.")
                    elif p != cp:
                        st.error("Passwords do not match.")
                    elif len(p) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        if register_user(u, p):
                            st.session_state.reset_success_msg = "✓ Account created successfully! Please sign in."
                            st.session_state.auth_mode = "login"
                            st.rerun()
                        else:
                            st.error("Username already taken. Choose another.")

            st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
            if st.button("←  Back to Sign In", key="back_signin_btn", use_container_width=True):
                st.session_state.auth_mode = "login"
                st.rerun()

        # ════════════════════
        # RESET PASSWORD MODE
        # ════════════════════
        elif st.session_state.auth_mode == "reset":
            with st.form("reset_form", clear_on_submit=True):
                st.markdown("""
                <div style="text-align:center;padding-bottom:10px;margin-bottom:20px">
                    <div style="width:44px;height:44px;background:linear-gradient(135deg,#F59E0B,#EF4444);
                        border-radius:13px;display:inline-flex;align-items:center;justify-content:center;
                        font-size:20px;box-shadow:0 4px 14px rgba(239,68,68,.20);margin-bottom:11px">🔑</div>
                    <div style="font-size:19px;font-weight:700;color:#111827;letter-spacing:-.3px;
                        margin-bottom:4px;font-family:'Inter',sans-serif">Reset Password</div>
                    <div style="font-size:13px;color:#9CA3AF;font-family:'Inter',sans-serif">
                        Enter your username and choose a new password</div>
                </div>
                <div class="auth-info-box">
                    <span style="font-size:15px;margin-top:1px">ℹ️</span>
                    <span class="auth-info-text">
                        No email verification needed — your account is stored<br>locally on this machine.
                    </span>
                </div>
                """, unsafe_allow_html=True)

                r_user = st.text_input("Username", placeholder="Your username", key="rp_user")
                r_new  = st.text_input("New Password", type="password",
                                       placeholder="Min. 6 characters", key="rp_new")
                r_conf = st.text_input("Confirm New Password", type="password",
                                       placeholder="Repeat new password", key="rp_conf")
                ok_reset = st.form_submit_button("Reset Password  →", use_container_width=True)
                
                if ok_reset:
                    ru, rp, rc = r_user.strip(), r_new.strip(), r_conf.strip()
                    if not ru or not rp:
                        st.error("Please fill in all fields.")
                    elif not user_exists(ru):
                        st.error("Username not found. Check the spelling.")
                    elif rp != rc:
                        st.error("Passwords do not match.")
                    elif len(rp) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        if reset_password(ru, rp):
                            st.session_state.reset_success_msg = "✓ Password reset successfully! Please sign in with your new password."
                            st.session_state.auth_mode = "login"
                            st.rerun()
                        else:
                            st.error("Something went wrong. Please try again.")

            st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
            if st.button("←  Back to Sign In", key="back_signin_btn", use_container_width=True):
                st.session_state.auth_mode = "login"
                st.rerun()

    st.stop()




# ─────────────────────────────────────────────
# POST-LOGIN WELCOME TOAST
# ─────────────────────────────────────────────
if st.session_state.show_login_toast:
    st.toast(f"Welcome back, {st.session_state.username}! 👋")
    st.balloons()
    st.session_state.show_login_toast = False

# ─────────────────────────────────────────────
# LOAD PERSISTED FAISS INDEX
# ─────────────────────────────────────────────
if st.session_state.vector_store is None:
    idx_dir = f"faiss_index_{st.session_state.username}"
    if os.path.exists(idx_dir) and os.path.exists(f"{idx_dir}_meta.json"):
        try:
            with open(f"{idx_dir}_meta.json") as f:
                stats = json.load(f)
            provider = stats.get("embed_provider", "Google Gemini")
            
            # Enforce Demo Mode lock
            if os.getenv("IS_DEMO_MODE") == "true" and provider != "Groq + HuggingFace (Free)":
                provider = "Groq + HuggingFace (Free)"

            emb = None
            # If saved index used Gemini but key is missing/expired → auto-switch to HuggingFace
            if provider == "Google Gemini":
                key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if key:
                    emb = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=key)
                elif _HF_AVAILABLE:
                    # Silently fall back to HuggingFace — user will need to re-upload
                    st.session_state.sel_embed = "Groq + HuggingFace (Free)"
                    st.session_state.embed_provider = "Groq + HuggingFace (Free)"
                    # Don't load stale Gemini index — force re-upload with new provider
                    emb = None
            elif provider == "Groq + HuggingFace (Free)" and _HF_AVAILABLE:
                emb = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True}
                )
            else:
                key = os.getenv("OPENAI_API_KEY")
                if key:
                    emb = OpenAIEmbeddings(api_key=key)
            if emb:
                st.session_state.vector_store = FAISS.load_local(
                    idx_dir, emb, allow_dangerous_deserialization=True)
                st.session_state.document_stats = stats
                st.session_state.embed_provider = provider
                st.session_state.sel_embed = provider
        except Exception:
            # If loading fails for any reason (e.g., expired key during FAISS load), skip silently
            pass

# ══════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════
with st.sidebar:
    # ── Header ──
    st.markdown(f"""
    <div class="sb-header">
        <div class="sb-header-icon">📄</div>
        <div>
            <div class="sb-header-name">IntelliDocs AI</div>
            <div class="sb-header-sub">Document Intelligence Hub</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── New Chat ──
    if st.button("＋  New Conversation", use_container_width=True, key="btn_new_chat"):
        st.session_state.current_thread_id = None
        st.session_state.chat_history = []
        st.rerun()

    # ── Thread List ──
    threads = get_threads(st.session_state.username)
    if threads:
        st.markdown('<div class="sb-section">Recent Chats</div>', unsafe_allow_html=True)
        for tid, ttitle, _ in threads:
            label = ("💬  " + ttitle[:26] + ("…" if len(ttitle) > 26 else ""))
            is_active = (tid == st.session_state.current_thread_id)
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"t_{tid}", use_container_width=True, type=btn_type):
                st.session_state.current_thread_id = tid
                st.session_state.chat_history = get_messages(tid)
                st.rerun()
        if st.session_state.current_thread_id:
            if st.button("🗑  Delete conversation", use_container_width=True, key="btn_del"):
                delete_thread(st.session_state.current_thread_id)
                st.session_state.current_thread_id = None
                st.session_state.chat_history = []
                st.rerun()

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # ── User + logout ──
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 10px; padding: 4px 4px 10px;">
        <div style="width: 34px; height: 34px; background: linear-gradient(135deg, #6366F1, #8B5CF6); color: white; 
            border-radius: 50%; display: flex; align-items: center; justify-content: center; 
            font-weight: 700; font-size: 14px; box-shadow: 0 2px 6px rgba(99,102,241,0.15);">
            {st.session_state.username[0].upper() if st.session_state.username else "U"}
        </div>
        <div style="display: flex; flex-direction: column; flex-grow: 1;">
            <span style="font-size: 13px; font-weight: 600; color: #111827; line-height: 1.2;">
                {st.session_state.username}
            </span>
            <span style="font-size: 10.5px; color: #9CA3AF; line-height: 1.2; margin-top: 1px;">
                IntelliDocs User
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("Log Out  🚪", key="btn_logout", use_container_width=True):
        for k in list(DEFAULTS.keys()):
            st.session_state[k] = DEFAULTS[k]
        st.rerun()

# ══════════════════════════════════════════════
# TOP BAR
# ══════════════════════════════════════════════
provider = st.session_state.get("sel_prov", "Google Gemini")

# Validate model selection based on provider to prevent sync lag
if provider == "OpenAI":
    models_list = ["gpt-4o-mini", "gpt-4o"]
elif provider == "Google Gemini":
    models_list = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
else:
    models_list = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]

model = st.session_state.get("sel_model")
if model not in models_list:
    model = models_list[0]
    st.session_state.sel_model = model

temp = st.session_state.get("sld_temp", 0.2)

doc_n   = len(st.session_state.document_stats.get("files", []))
doc_lbl = f"{doc_n} file{'s' if doc_n!=1 else ''} indexed" if doc_n else "No documents loaded"
chat_title = "New Conversation"
if st.session_state.current_thread_id:
    for tid, ttitle, _ in get_threads(st.session_state.username):
        if tid == st.session_state.current_thread_id:
            chat_title = ttitle; break

st.markdown(f"""
<div class="topbar">
    <div class="topbar-left">
        <div class="topbar-icon">💬</div>
        <div>
            <div class="topbar-title">{chat_title}</div>
            <div class="topbar-sub">{doc_lbl} · {provider} / {model}</div>
        </div>
    </div>
    <div class="topbar-pill">
        <span class="topbar-pill-dot"></span>
        {provider}
    </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# MAIN WORKSPACE (CHAT & CONTROL PANEL)
# ══════════════════════════════════════════════
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

col_chat, col_panel = st.columns([2.3, 1.0])

# ── LEFT COLUMN: CHAT INTERFACE ──
with col_chat:
    if not st.session_state.chat_history:
        st.markdown("""
        <div class="empty-wrap">
            <span class="empty-icon">💬</span>
            <div class="empty-h">Ready to explore your documents</div>
            <div class="empty-p">
                Upload PDF, DOCX, TXT or CSV files from the right panel,<br>
                then ask anything — get instant AI-powered answers.
            </div>
            <div class="sg-grid">
                <div class="sg-card"><span class="sg-icon">📋</span>Summarize the main findings</div>
                <div class="sg-card"><span class="sg-icon">🔍</span>What are the key conclusions?</div>
                <div class="sg-card"><span class="sg-icon">📊</span>Extract all statistics</div>
                <div class="sg-card"><span class="sg-icon">❓</span>List all open questions</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sources") and msg["role"] == "assistant":
                    with st.expander("📚 View sources"):
                        for s in msg["sources"]:
                            st.markdown(
                                f"<span style='background:#EEF2FF;border:1px solid #C7D2FE;"
                                f"border-radius:20px;padding:3px 11px;font-size:12px;"
                                f"color:#4338CA;font-weight:500;display:inline-block;margin:3px 4px 3px 0'>"
                                f"📄 {s['file']} · p{s['page']}</span>",
                                unsafe_allow_html=True)
                            st.caption(f'"{s["text"][:200]}…"')

    # Export button
    if st.session_state.chat_history:
        c1, c2 = st.columns([8,1])
        with c2:
            st.download_button("📥 Export", data=export_chat(),
                file_name=f"intellidocs_{st.session_state.current_thread_id or 'chat'}.md",
                mime="text/markdown", key="btn_export")

    # Chat input
    if query := st.chat_input("Ask a question about your documents…", key="chat_in"):
        if not st.session_state.vector_store:
            with st.chat_message("user"):
                st.markdown(query)
            with st.chat_message("assistant"):
                st.markdown("📂 Please upload at least one document in the **Documents Panel** on the right before asking questions.")
        else:
            if not st.session_state.current_thread_id:
                tid = str(uuid.uuid4())
                create_thread(tid, query[:32]+"…" if len(query)>32 else query, st.session_state.username)
                st.session_state.current_thread_id = tid

            save_message(st.session_state.current_thread_id, "user", query)
            st.session_state.chat_history.append({"role":"user","content":query})

            with st.chat_message("user"):
                st.markdown(query)

            with st.chat_message("assistant"):
                try:
                    from agents import create_agent_graph
                    
                    with st.status("🤖 Orchestrating Multi-Agent Workflow...", expanded=True) as status:
                        status.write("🔍 **Retrieval Agent**: Fetching document chunks and evaluating relevance...")
                        
                        graph = create_agent_graph()
                        
                        initial_state = {
                            "query": query,
                            "chat_history": st.session_state.chat_history[:-1],  # Exclude current user query
                            "vector_store": st.session_state.vector_store,
                            "provider": provider,
                            "model": model,
                            "temperature": temp,
                            "retrieved_docs": [],
                            "relevance_scores": [],
                            "summarized_context": "",
                            "verification_report": {},
                            "final_answer": "",
                            "sources": []
                        }
                        
                        final_state = initial_state
                        
                        # Stream the node updates to show execution step-by-step
                        for event in graph.stream(initial_state, stream_mode="updates"):
                            for node, state_update in event.items():
                                if node == "retrieval":
                                    rdocs = state_update.get("retrieved_docs", [])
                                    scores = state_update.get("relevance_scores", [])
                                    status.write(f"✅ **Retrieval Agent**: Retrieved {len(rdocs)} chunks (Relevance scores: {scores})")
                                    status.write("📝 **Summarization Agent**: Synthesizing context chunks and removing redundancies...")
                                    final_state.update(state_update)
                                elif node == "summarization":
                                    status.write("✅ **Summarization Agent**: Synthetic context summary compiled.")
                                    status.write("🛡️ **Fact Verification Agent**: Checking summary against raw document context...")
                                    final_state.update(state_update)
                                elif node == "verification":
                                    report = state_update.get("verification_report", {})
                                    status.write(f"✅ **Fact Verification Agent**: Status: `{report.get('status')}`. Hallucinations: `{report.get('hallucinations_detected')}`.")
                                    status.write("✍️ **Answer Generation Agent**: Formulating final response with citations...")
                                    final_state.update(state_update)
                                elif node == "generation":
                                    status.write("✅ **Answer Generation Agent**: Final response drafted.")
                                    final_state.update(state_update)
                                    
                        status.update(label="🤖 Multi-Agent Workflow Completed!", state="complete")
                    
                    final_answer = final_state.get("final_answer", "Error: No answer generated.")
                    sources = final_state.get("sources", [])
                    
                    # Stream the output token-by-token for responsive UI feel
                    def stream_text(text):
                        for char in text:
                            yield char
                            time.sleep(0.002)
                    
                    full_response = st.write_stream(stream_text(final_answer))
                    st.session_state.chat_history.append({"role": "assistant", "content": full_response, "sources": sources})
                    save_message(st.session_state.current_thread_id, "assistant", full_response, sources)
                    st.rerun()
                    
                except Exception as e:
                    err_s = str(e)
                    if "API_KEY_INVALID" in err_s or "expired" in err_s.lower() or "API key expired" in err_s:
                        friendly = "🔑 **Your API key has expired or is invalid.** Please go to the **⚙️ Model Controls** tab and check your keys or switch provider."
                        st.error(friendly)
                        st.session_state.chat_history.append({"role":"assistant","content":friendly})
                        save_message(st.session_state.current_thread_id, "assistant", friendly)
                    elif "429" in err_s or "RESOURCE_EXHAUSTED" in err_s or "quota" in err_s.lower():
                        import re
                        wait_match = re.search(r"retry in (\d+)", err_s)
                        wait_secs = wait_match.group(1) if wait_match else "60"
                        friendly = (
                            f"⏳ **Model is currently rate-limited** (free tier quota reached).\n\n"
                            f"Please wait **~{wait_secs} seconds** and try again, or switch to **Groq** "
                            f"(free & fast) in the ⚙️ Model Controls panel."
                        )
                        st.warning(friendly)
                    else:
                        err = f"❌ Error: {err_s}"
                        st.error(err)
                        st.session_state.chat_history.append({"role":"assistant","content":err})
                        save_message(st.session_state.current_thread_id, "assistant", err)

# ── RIGHT COLUMN: WORKSPACE PANEL (DOCUMENTS & CONTROLS) ──
with col_panel:
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    with st.container(key="workspace_panel"):
        tab_docs, tab_model = st.tabs(["📂 Documents", "⚙️ Model Controls"])
        
        # ── Documents Tab ──
        with tab_docs:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            embed_options = ["Groq + HuggingFace (Free)", "Google Gemini", "OpenAI"]
            
            api_demo_mode = os.getenv("IS_DEMO_MODE") == "true"
            if api_demo_mode:
                embed_options = ["Groq + HuggingFace (Free)"]
                if st.session_state.get("sel_embed") != "Groq + HuggingFace (Free)":
                    st.session_state.sel_embed = "Groq + HuggingFace (Free)"
                    
            try:
                embed_idx = embed_options.index(st.session_state.get("sel_embed", "Groq + HuggingFace (Free)"))
            except ValueError:
                embed_idx = 0
                
            embed_choice = st.selectbox(
                "Embedding Model",
                embed_options,
                index=embed_idx,
                key="sel_embed_widget",
                help="Groq + HuggingFace: runs locally, no API key needed. Best free option!"
            )
            
            if embed_choice != st.session_state.get("sel_embed"):
                st.session_state.sel_embed = embed_choice
                st.rerun()

            if embed_choice == "Groq + HuggingFace (Free)" and not _HF_AVAILABLE:
                st.warning("⚠️ HuggingFace packages not installed. Run: `pip install langchain-huggingface sentence-transformers`")
            if embed_choice != st.session_state.embed_provider:
                st.session_state.embed_provider  = embed_choice
                st.session_state.vector_store    = None
                st.session_state.document_stats  = {"pages":0,"chunks":0,"files":[]}
                st.warning("Embedding changed — re-upload files.")
            if embed_choice == "Groq + HuggingFace (Free)":
                st.markdown("""
                <div style="margin-top:6px;padding:8px 10px;background:#F0FDF4;border:1px solid #BBF7D0;
                            border-radius:8px;font-size:11.5px;color:#166534;line-height:1.5">
                    ✅ <b>No API key required.</b> Uses <code>all-MiniLM-L6-v2</code> locally.<br>
                    Perfect free pairing with the <b>Groq</b> LLM provider.
                </div>
                """, unsafe_allow_html=True)

            uploaded_files = st.file_uploader(
                "Upload PDF, DOCX, TXT, CSV",
                type=["pdf","docx","txt","csv"],
                accept_multiple_files=True, key="fu")
            if uploaded_files:
                names = [f.name for f in uploaded_files]
                if names != st.session_state.document_stats["files"] or not st.session_state.vector_store:
                    with st.spinner("Indexing documents…"):
                        raw = []
                        for f in uploaded_files: raw.extend(extract_text_from_file(f))
                        if raw:
                            res = build_vectorstore(raw, embed_choice)
                            if res:
                                vs, chunks = res
                                idx_dir = f"faiss_index_{st.session_state.username}"
                                vs.save_local(idx_dir)
                                st.session_state.vector_store   = vs
                                st.session_state.document_stats = {
                                    "pages": len(raw),
                                    "chunks": chunks,
                                    "files": names,
                                    "embed_provider": embed_choice
                                }
                                with open(f"{idx_dir}_meta.json","w") as fj:
                                    json.dump(st.session_state.document_stats, fj)
                                st.success(f"✓ {len(names)} file(s) indexed successfully!")
                                st.balloons()
                        else: st.warning("⚠️ No readable text found in the uploaded file(s). This usually means your PDF is image/scan-based and has no text layer. Try a PDF with selectable text.")

            if st.session_state.vector_store:
                ds = st.session_state.document_stats
                st.markdown(f"""
                <div class="sb-stat-card" style="margin-top: 14px;">
                    <div class="sb-stat-row">
                        <span class="sb-stat-lbl">Files</span>
                        <span class="sb-stat-val">{len(ds['files'])}</span>
                    </div>
                    <div class="sb-stat-row">
                        <span class="sb-stat-lbl">Pages / Sections</span>
                        <span class="sb-stat-val">{ds['pages']}</span>
                    </div>
                    <div class="sb-stat-row">
                        <span class="sb-stat-lbl">Vector chunks</span>
                        <span class="sb-stat-val">{ds['chunks']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("✨  Summarize Documents", use_container_width=True, key="btn_sum"):
                    with st.spinner("Generating summary…"):
                        try:
                            sdocs = st.session_state.vector_store.similarity_search(
                                "overview introduction summary highlights takeaways", k=6)
                            ctx = "\n\n".join(d.page_content for d in sdocs)
                            prompt = ("You are a Document Intelligence Analyst.\n"
                                      "Write a professional executive summary with:\n"
                                      "1. **Overview** 2. **Key Takeaways** 3. **Main Topics**\n"
                                      "Use clean markdown.\n\n"
                                      f"--- FRAGMENTS ---\n{ctx}\n-----------------")
                            if not st.session_state.current_thread_id:
                                tid = str(uuid.uuid4())
                                create_thread(tid, "Document Summary", st.session_state.username)
                                st.session_state.current_thread_id = tid
                            save_message(st.session_state.current_thread_id, "user", "Generate document summary.")
                            st.session_state.chat_history.append({"role":"user","content":"Generate document summary."})
                            llm_stream, used_model = invoke_llm_with_fallback(
                                provider, model, temp,
                                [("system", prompt),
                                 ("human", "Please write the executive summary of the document fragments now.")]
                            )
                            if used_model != model:
                                st.toast(f"⚡ Switched to {used_model} (rate limit)", icon="⚡")
                            # invoke_llm_with_fallback returns a stream — collect it
                            full_parts = []
                            for chunk in llm_stream:
                                if hasattr(chunk, 'content'):
                                    full_parts.append(chunk.content)
                                elif isinstance(chunk, str):
                                    full_parts.append(chunk)
                            reply = "".join(full_parts)
                            st.session_state.chat_history.append({"role":"assistant","content":reply})
                            save_message(st.session_state.current_thread_id, "assistant", reply)
                            st.rerun()
                        except Exception as e:
                            err_s = str(e)
                            if "API_KEY_INVALID" in err_s or "expired" in err_s.lower() or "API key expired" in err_s:
                                st.error("🔑 **Your Gemini API key has expired.** Please go to the **⚙️ Model Controls** tab and switch your provider to **Groq**.")
                            else:
                                st.error(f"Error: {e}")

        # ── Model Controls Tab ──
        with tab_model:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            
            api_demo_mode = os.getenv("IS_DEMO_MODE") == "true"
            prov_options = ["Google Gemini", "Groq", "OpenAI"]
            if api_demo_mode:
                st.markdown("""
                <div style="padding:10px 12px;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.3);
                            border-radius:10px;font-size:12px;color:#818CF8;line-height:1.5;margin-bottom:12px;">
                    ⚡ <b>Demo Mode Active</b><br>
                    Only the free <b>Groq Llama 3</b> models are available in this public preview to prevent API abuse.
                </div>
                """, unsafe_allow_html=True)
                prov_options = ["Groq"]
                if st.session_state.get("sel_prov") != "Groq":
                    st.session_state.sel_prov = "Groq"
                    
            try:
                prov_idx = prov_options.index(st.session_state.get("sel_prov", "Google Gemini"))
            except ValueError:
                prov_idx = 0
                
            prov_choice = st.selectbox("LLM Provider", prov_options, index=prov_idx, key="sel_prov_widget")
            if prov_choice != st.session_state.get("sel_prov"):
                st.session_state.sel_prov = prov_choice
                st.rerun()

            if prov_choice == "OpenAI":
                models, api_ok = ["gpt-4o-mini","gpt-4o"], bool(os.getenv("OPENAI_API_KEY"))
            elif prov_choice == "Google Gemini":
                models, api_ok = ["gemini-2.5-flash","gemini-2.5-pro","gemini-2.0-flash"], bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
            else:
                models, api_ok = ["llama-3.3-70b-versatile","mixtral-8x7b-32768"], bool(os.getenv("GROQ_API_KEY"))
                
            try:
                model_idx = models.index(st.session_state.get("sel_model"))
            except ValueError:
                model_idx = 0
            model_choice = st.selectbox("Model", models, index=model_idx, key="sel_model_widget")
            if model_choice != st.session_state.get("sel_model"):
                st.session_state.sel_model = model_choice
                st.rerun()

            temp_choice = st.slider("Temperature", 0.0, 1.0, value=float(st.session_state.get("sld_temp", 0.2)), step=0.05, key="sld_temp_widget")
            if temp_choice != st.session_state.get("sld_temp"):
                st.session_state.sld_temp = temp_choice
                st.rerun()

            dot_cls = "sb-dot-ok" if api_ok else "sb-dot-err"
            status_txt = f"{prov_choice} connected" if api_ok else f"{prov_choice} key missing"
            st.markdown(f'<div class="sb-status" style="margin-top: 12px;"><span class="{dot_cls}"></span>{status_txt}</div>',
                        unsafe_allow_html=True)

            # Show Groq setup hint if Gemini is selected but Groq key is missing
            if prov_choice == "Google Gemini" and not os.getenv("GROQ_API_KEY"):
                st.markdown("""
                <div style="margin-top:12px;padding:10px 12px;background:#FFFBEB;border:1px solid #FDE68A;
                            border-radius:10px;font-size:12px;color:#92400E;line-height:1.5">
                    <b>💡 Gemini free tier has daily limits.</b><br>
                    Add a free <b>Groq API key</b> to use Llama 3 as unlimited backup:<br>
                    <code style="background:#FEF3C7;padding:2px 5px;border-radius:4px">
                    GROQ_API_KEY=... in your .env</code><br>
                    <a href="https://console.groq.com/keys" target="_blank"
                       style="color:#D97706;font-weight:600">→ Get free key at console.groq.com</a>
                </div>
                """, unsafe_allow_html=True)
