"""Streamlit main application — Research RAG."""

import logging
import uuid

import streamlit as st

import config
from config import SESSION_DIR

config.setup_logging("app")
logger = logging.getLogger("app")

from src.rag.engine import RAGEngine  # noqa: E402
from src.ui.session import SessionManager  # noqa: E402

st.set_page_config(
    page_title="리서처헬퍼",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
#
# Root cause of previous bug:
#   Streamlit wraps every st.* element in an extra wrapper div, so the adjacent-
#   sibling selector  stMarkdown + stPopover  never matched in the real DOM.
#
# Fix: target the only popover in the app via .stMainBlockContainer [data-testid="stPopover"]
# This is safe because we have exactly one st.popover() call in the entire app.

_BASE_CSS = """<style>
/* ── Streamlit chrome cleanup ──────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none !important; }

/* ── Chat layout: User → RIGHT ─────────────────────────────────────── */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    justify-content: flex-end;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
    [data-testid="stChatMessageAvatarContainer"] { display: none !important; }

/* ── Slide-in animations ────────────────────────────────────────────── */
@keyframes slideFromRight {
    from { opacity: 0; transform: translateX(24px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes slideFromLeft {
    from { opacity: 0; transform: translateX(-24px); }
    to   { opacity: 1; transform: translateX(0); }
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    animation: slideFromRight 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    animation: slideFromLeft 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
}

/* ── Fixed header bar (visual shell) ────────────────────────────────── */
.app-header {
    position: fixed; top: 0; left: 0; right: 0;
    height: 52px; z-index: 9998;
    display: flex; align-items: center;
    padding: 0 2rem;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    transition: background 0.3s;
}
.app-header-logo {
    font-size: 1.1rem; font-weight: 400;
    letter-spacing: 0.08em; user-select: none;
}

/* Push content below the fixed header */
.stMainBlockContainer { padding-top: 66px !important; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 52px !important; }

/* ── Hamburger menu button: position: fixed into the header ──────────
   The only st.popover() in this app is the menu button.
   Direct targeting avoids broken sibling/wrapper-div selectors.         */
.stMainBlockContainer [data-testid="stPopover"] {
    position: fixed !important;
    top: 10px !important;
    right: 2rem !important;
    z-index: 99999 !important;
}
/* Popover dropdown sits just below the header */
[data-testid="stPopoverContent"] { z-index: 100000 !important; }

/* Popover trigger button — base style (color set per theme) */
.stMainBlockContainer [data-testid="stPopover"] [data-testid="stBaseButton-secondary"] {
    background: transparent !important;
    border: 1px solid rgba(74, 143, 205, 0.35) !important;
    border-radius: 8px !important;
    font-size: 1.05rem !important;
    padding: 5px 12px !important;
    min-height: 32px !important;
    line-height: 1 !important;
    transition: all 0.22s !important;
}
.stMainBlockContainer [data-testid="stPopover"] [data-testid="stBaseButton-secondary"]:hover {
    background: rgba(74, 143, 205, 0.14) !important;
    border-color: #4a8fcd !important;
    transform: none !important;
}

/* ── Scrollbar ──────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
</style>"""

# ── Dark theme ────────────────────────────────────────────────────────────────
_DARK_THEME = """<style>
/* Header */
.app-header {
    background: rgba(8, 14, 24, 0.88);
    border-bottom: 1px solid rgba(26, 46, 72, 0.75);
}
.app-header-logo { color: #c0d8f0; }
.stMainBlockContainer [data-testid="stPopover"] button { color: #a0c8e8 !important; }

/* Chat bubbles */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
    [data-testid="stChatMessageContent"] {
    max-width: 70% !important;
    background: linear-gradient(140deg, #1b3d72, #1d4a8a) !important;
    border-radius: 16px 4px 16px 16px !important;
    border: 1px solid #2a5aa8 !important;
    box-shadow: 0 3px 16px rgba(0, 30, 90, 0.45) !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
    [data-testid="stChatMessageContent"] {
    max-width: 76% !important;
    background: linear-gradient(140deg, #111d2c, #162438) !important;
    border-radius: 4px 16px 16px 16px !important;
    border: 1px solid #1f3550 !important;
    box-shadow: 0 3px 16px rgba(0, 10, 40, 0.45) !important;
}
[data-testid="stChatMessageAvatarContainer"] {
    background: #172a40 !important; border: 1px solid #2a4870 !important;
    border-radius: 50% !important;
}

/* Chat input */
[data-testid="stChatInput"] {
    background: #111e2d !important; border-radius: 28px !important;
    border: 1px solid #243b58 !important;
    box-shadow: 0 4px 20px rgba(0, 20, 60, 0.4) !important;
    padding: 4px 8px !important;
}
[data-testid="stChatInput"] > div { border: none !important; background: transparent !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #090f1a 0%, #0d1828 100%) !important;
    border-right: 1px solid #1a2e48 !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: #112035 !important; color: #7ab3d9 !important;
    border: 1px solid #1e3655 !important; border-radius: 10px !important;
    transition: all 0.25s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #1a3a6b !important; border-color: #4a8fcd !important;
    color: #ddf0ff !important; box-shadow: 0 0 16px rgba(74,143,205,0.25) !important;
    transform: translateY(-1px) !important;
}
.sidebar-title { color: #8bbde0 !important; }
.sidebar-meta  { color: #3a5a7a !important; }

/* Misc */
hr { border-color: #1a2e48 !important; opacity: 1 !important; }
.stSpinner > div { border-top-color: #4a8fcd !important; }
::-webkit-scrollbar-track { background: #0a1420; }
::-webkit-scrollbar-thumb { background: #203550; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #2e4f78; }
</style>"""

# ── Light theme ───────────────────────────────────────────────────────────────
# config.toml injects dark colors as CSS variables. We override them here with
# both variable redefinition and explicit !important rules on key elements.
_LIGHT_THEME = """<style>
/* Override Streamlit CSS variables (config.toml theme) */
:root {
    --text-color: #1a2a40 !important;
    --background-color: #f0f5fc !important;
    --secondary-background-color: #e4eef8 !important;
}

/* Header */
.app-header {
    background: rgba(244, 249, 255, 0.92);
    border-bottom: 1px solid rgba(184, 204, 228, 0.8);
}
.app-header-logo { color: #1a2a40 !important; }
.stMainBlockContainer [data-testid="stPopover"] button { color: #1a3a6b !important; }
.stMainBlockContainer [data-testid="stPopover"]
    [data-testid="stBaseButton-secondary"]:hover { background: rgba(26,58,107,0.1) !important; }

/* Base backgrounds */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.stMainBlockContainer,
.block-container { background-color: #f0f5fc !important; }

/* Global text — override dark textColor from config.toml */
.stApp, .stApp p, .stApp span, .stApp div,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp li, .stApp td, .stApp th, .stApp label,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] * { color: #1a2a40 !important; }
.stCaption, .stCaption * { color: #4a6a8a !important; }
/* Welcome message inline colors — override via element type */
.stMainBlockContainer [data-testid="stMarkdownContainer"] h2 { color: #1a3a6b !important; }

/* Chat bubbles */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
    [data-testid="stChatMessageContent"] {
    max-width: 70% !important;
    background: linear-gradient(140deg, #2a5595, #1e4a8a) !important;
    border-radius: 16px 4px 16px 16px !important;
    border: 1px solid #1a3d70 !important;
    box-shadow: 0 3px 16px rgba(0, 30, 90, 0.18) !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
    [data-testid="stChatMessageContent"] * { color: #ffffff !important; }

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
    [data-testid="stChatMessageContent"] {
    max-width: 76% !important;
    background: linear-gradient(140deg, #edf3fc, #e4eef8) !important;
    border-radius: 4px 16px 16px 16px !important;
    border: 1px solid #b8cce4 !important;
    box-shadow: 0 2px 10px rgba(30, 80, 150, 0.1) !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
    [data-testid="stChatMessageContent"] * { color: #1a2a40 !important; }

[data-testid="stChatMessageAvatarContainer"] {
    background: #dce8f5 !important; border: 1px solid #9ab8d8 !important;
    border-radius: 50% !important;
}

/* Chat input */
[data-testid="stChatInput"] {
    background: #ffffff !important; border-radius: 28px !important;
    border: 1px solid #b8cce4 !important;
    box-shadow: 0 2px 12px rgba(30, 80, 150, 0.1) !important;
    padding: 4px 8px !important;
}
[data-testid="stChatInput"] > div { border: none !important; background: transparent !important; }
/* Input placeholder and typed text */
[data-testid="stChatInput"] textarea { color: #1a2a40 !important; }
[data-testid="stChatInput"] textarea::placeholder { color: #7090b0 !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #dce8f5 0%, #e8f0fa 100%) !important;
    border-right: 1px solid #b8cce4 !important;
}
section[data-testid="stSidebar"] * { color: #1a2a40 !important; }
section[data-testid="stSidebar"] .stButton > button {
    background: #e0ecf8 !important; color: #1a3a6b !important;
    border: 1px solid #9ab8d8 !important; border-radius: 10px !important;
    transition: all 0.25s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #c8dff5 !important; border-color: #2a5a9a !important;
    color: #0a1f40 !important; transform: translateY(-1px) !important;
}
.sidebar-title { color: #1a3a6b !important; }
.sidebar-meta  { color: #5a7a9a !important; }

/* Toggle (dark mode switch inside popover) */
[data-testid="stToggleSwitch"] label { color: #1a2a40 !important; }

/* Misc */
hr { border-color: #b8cce4 !important; opacity: 1 !important; }
::-webkit-scrollbar-track { background: #e8f0f8; }
::-webkit-scrollbar-thumb { background: #9ab8d8; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #7098c0; }
</style>"""


# ─── Per-user session state ───────────────────────────────────────────────────
#
# @st.cache_resource creates a single shared instance across ALL users.
# RAGEngine holds ConversationBufferMemory — sharing it leaks chat history
# between users. Instead, each browser connection gets its own engine and
# session manager stored in st.session_state (which is per-connection).
#
# user_ns: a UUID assigned once per browser tab, used to namespace the
# session files directory so users never see each other's history.

def _init_state() -> None:
    defaults: dict = {
        "initialized": False,
        "messages": [],
        "engine_ready": False,
        "session_id": None,
        "dark_mode": True,
        "user_ns": str(uuid.uuid4()),  # unique namespace per browser connection
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

if not st.session_state.initialized:
    try:
        # Engine: per-user instance — never shared between connections
        if "engine" not in st.session_state:
            with st.spinner("AI 엔진 초기화 중..."):
                st.session_state.engine = RAGEngine()

        # Session manager: per-user directory so load_latest_session()
        # only sees files created by this connection
        if "session_manager" not in st.session_state:
            user_session_dir = SESSION_DIR / st.session_state.user_ns
            st.session_state.session_manager = SessionManager(session_dir=user_session_dir)

        _eng: RAGEngine = st.session_state.engine
        _sm: SessionManager = st.session_state.session_manager

        latest = _sm.load_latest_session()
        if latest:
            st.session_state.session_id = latest["session_id"]
            st.session_state.messages = [
                {"role": m["role"], "content": m["content"]}
                for m in latest.get("messages", [])
            ]
            try:
                mem = _sm.rebuild_memory(latest["session_id"])
                if mem:
                    _eng.load_memory_messages(mem)
            except Exception as _e:
                logger.warning("메모리 복원 실패: %s", _e)
        else:
            st.session_state.session_id = _sm.create_session()
        st.session_state.engine_ready = True
    except EnvironmentError as _e:
        logger.critical("환경 변수 오류: %s", _e)
    except Exception as _e:
        logger.critical("엔진 초기화 실패: %s", _e)
    finally:
        st.session_state.initialized = True

if not st.session_state.engine_ready:
    st.error(
        "**RAG 엔진 시작 실패**\n\n"
        "`.env` 파일의 `OPENAI_API_KEY`, `PINECONE_API_KEY`를 확인하세요."
    )
    st.stop()

engine: RAGEngine = st.session_state.engine
session_manager: SessionManager = st.session_state.session_manager


# ─── Base CSS (always applied) ────────────────────────────────────────────────
st.markdown(_BASE_CSS, unsafe_allow_html=True)

# ─── Fixed header bar (visual shell — logo only) ──────────────────────────────
st.markdown(
    '<div class="app-header">'
    '<span class="app-header-logo">🧬 리서처헬퍼</span>'
    '</div>',
    unsafe_allow_html=True,
)

# ─── Hamburger menu (CSS positions this fixed into the header's right side) ───
with st.popover("☰", use_container_width=False):
    st.markdown(
        "<p style='font-size:0.72rem; font-weight:600; letter-spacing:0.1em; "
        "opacity:0.55; margin:0 0 0.6rem; text-transform:uppercase;'>화면 설정</p>",
        unsafe_allow_html=True,
    )
    dark_mode = st.toggle(
        "🌙 다크 모드",
        value=st.session_state.dark_mode,
        key="dm_toggle",
    )
    st.session_state.dark_mode = dark_mode

# Theme CSS injected after reading dark_mode so it reflects current state
st.markdown(_DARK_THEME if st.session_state.dark_mode else _LIGHT_THEME, unsafe_allow_html=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<h2 class='sidebar-title' style='font-weight:300; margin-bottom:0; "
        "letter-spacing:0.04em;'>🧬 리서처헬퍼</h2>",
        unsafe_allow_html=True,
    )
    st.caption("전문 연구자용 논문 Q&A 시스템")
    st.divider()

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        try:
            engine.reset()
            session_manager.delete_session(st.session_state.session_id)
        except Exception:
            pass
        st.session_state.messages = []
        st.session_state.session_id = session_manager.create_session()
        st.rerun()

    st.divider()

    st.markdown(
        "<a href='mailto:upustream@gmail.com"
        "?subject=논문+데이터+추가+요청"
        "&body=안녕하세요.%0A추가를+요청할+논문+정보를+아래에+입력해+주세요.%0A%0A논문명:%0A저자:%0A출처/링크:' "
        "style='display:block; padding:9px 12px; text-decoration:none; "
        "border:1px dashed rgba(74,143,205,0.4); border-radius:8px; "
        "color:#5a9bd5; font-size:0.88rem; text-align:center;'>"
        "📧 논문 데이터 추가 요청</a>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='font-size:0.76rem; color:#4a6a8a; text-align:center; "
        "margin-top:0.55rem; line-height:1.65;'>"
        "직접 이메일을 보내시려면<br>"
        "<strong style='color:#5a9bd5;'>upustream@gmail.com</strong><br>"
        "으로 발송해 주세요.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
    st.divider()
    st.markdown(
        "<div class='sidebar-meta' style='text-align:center; font-size:0.75rem; line-height:1.9;'>"
        "v0.1&nbsp;·&nbsp;Developer&nbsp;<strong>shYOON</strong>"
        "</div>",
        unsafe_allow_html=True,
    )


# ─── Main chat area ───────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown(
        """
        <div style="
            display:flex; flex-direction:column; align-items:center;
            justify-content:center; padding:4rem 2rem 2rem; text-align:center;
        ">
            <div style="font-size:3rem; margin-bottom:1rem; opacity:0.75;">🧬</div>
            <h2 style="font-weight:300; font-size:1.8rem;
                margin-bottom:0.4rem; letter-spacing:0.05em;">리서처헬퍼</h2>
            <p style="color:#5a80a0; font-size:0.95rem;
                max-width:380px; line-height:1.75; margin:0;">
                논문·특허 문서를 기반으로 전문적인 질문에 답변합니다.<br>
                아래에 질문을 입력하세요.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ─── Chat input ───────────────────────────────────────────────────────────────
prompt = st.chat_input("논문이나 특허에 대해 질문하세요...")

if prompt:
    prompt = prompt.strip()
    if not prompt:
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    session_manager.save_message(st.session_state.session_id, "user", prompt)

    with st.chat_message("assistant"):
        answer = ""
        try:
            with st.spinner(""):
                source_docs, standalone_question = engine.prepare(prompt)

            if not source_docs:
                answer = "제공된 문서에서 해당 내용을 찾을 수 없습니다."
                st.markdown(answer)
            else:
                streamed = st.write_stream(
                    engine.generate_stream(standalone_question, source_docs)
                )
                answer = streamed if isinstance(streamed, str) else str(streamed)

            engine.update_history(prompt, answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})

            memory_msgs = engine.get_memory_messages()
            session_manager.save_message(
                st.session_state.session_id,
                "assistant",
                answer,
                memory_messages=memory_msgs,
            )

        except Exception as e:
            logger.error("Ask 처리 오류 (E-U-02): %s", e)
            answer = "⚠️ 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            st.markdown(answer)
            if (
                not st.session_state.messages
                or st.session_state.messages[-1]["role"] != "assistant"
            ):
                st.session_state.messages.append({"role": "assistant", "content": answer})
            session_manager.save_message(st.session_state.session_id, "assistant", answer)
