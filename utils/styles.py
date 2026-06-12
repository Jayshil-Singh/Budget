import streamlit as st

THEME_OPTIONS = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}


def init_theme_state():
    if "ui_theme" not in st.session_state:
        st.session_state["ui_theme"] = "system"


def sync_theme_from_user(user_id: int):
    """Load saved theme preference once per session."""
    if st.session_state.get("_theme_synced"):
        return
    from database import get_db
    from models.auth import User
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user and getattr(user, "ui_theme", None):
            st.session_state["ui_theme"] = user.ui_theme
    st.session_state["_theme_synced"] = True


def save_user_theme(user_id: int, theme: str):
    from database import get_db
    from models.auth import User
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.ui_theme = theme
            db.commit()


def render_theme_toggle(*, persist_user_id: int | None = None, use_sidebar: bool = False):
    """Light / dark / system appearance control."""
    init_theme_state()
    current = st.session_state.get("ui_theme", "system")
    keys = list(THEME_OPTIONS.keys())
    idx = keys.index(current) if current in keys else 0

    radio_kwargs = dict(
        label="Appearance",
        options=keys,
        index=idx,
        format_func=lambda k: THEME_OPTIONS[k],
        horizontal=True,
        key=f"theme_toggle_{'sb' if use_sidebar else 'main'}",
        help="System follows your device light/dark setting.",
    )
    if use_sidebar:
        choice = st.sidebar.radio(**radio_kwargs)
    else:
        choice = st.radio(**radio_kwargs)
    if choice != current:
        st.session_state["ui_theme"] = choice
        if persist_user_id:
            save_user_theme(persist_user_id, choice)
        st.rerun()


_BASE_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .app-title {
        font-weight: 700;
        background: linear-gradient(135deg, #00C9FF 0%, #92FE9D 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        margin-bottom: 0.2rem;
        text-align: left;
    }

    .app-subtitle {
        font-weight: 400;
        font-size: 1rem;
        margin-top: 0;
        margin-bottom: 2rem;
    }

    .glass-card {
        border-radius: 16px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    .kpi-container {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        border-radius: 12px;
        padding: 1.25rem;
        min-height: 120px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }

    .kpi-container:hover {
        transform: translateY(-2px);
        border-color: rgba(0, 201, 255, 0.4);
    }

    .kpi-label {
        font-size: 0.85rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .kpi-value {
        font-size: 1.6rem;
        font-weight: 700;
        margin-top: 0.5rem;
    }

    .status-pill {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        text-align: center;
    }

    .status-pill.critical { background-color: rgba(255, 82, 82, 0.15); color: #FF5252; border: 1px solid rgba(255, 82, 82, 0.3); }
    .status-pill.poor { background-color: rgba(255, 177, 66, 0.15); color: #FFB142; border: 1px solid rgba(255, 177, 66, 0.3); }
    .status-pill.good { background-color: rgba(0, 201, 255, 0.15); color: #00C9FF; border: 1px solid rgba(0, 201, 255, 0.3); }
    .status-pill.excellent { background-color: rgba(46, 213, 115, 0.15); color: #2ED573; border: 1px solid rgba(46, 213, 115, 0.3); }
    .status-pill.exceptional { background-color: rgba(146, 254, 157, 0.15); color: #92FE9D; border: 1px solid rgba(146, 254, 157, 0.3); }

    .calendar-cell { padding: 10px; border-radius: 8px; margin-bottom: 5px; font-size: 0.85rem; font-weight: 500; }
    .calendar-income { background-color: rgba(46, 213, 115, 0.15); color: #2ed573; border-left: 4px solid #2ed573; }
    .calendar-bill { background-color: rgba(255, 82, 82, 0.15); color: #ff5252; border-left: 4px solid #ff5252; }
    .calendar-savings { background-color: rgba(0, 201, 255, 0.15); color: #00c9ff; border-left: 4px solid #00c9ff; }
    .calendar-debt { background-color: rgba(255, 177, 66, 0.15); color: #ffb142; border-left: 4px solid #ffb142; }
    .calendar-goal { background-color: rgba(146, 254, 157, 0.15); color: #92fe9d; border-left: 4px solid #92fe9d; }
    .calendar-subscription { background-color: rgba(186, 85, 211, 0.15); color: #ba55d3; border-left: 4px solid #ba55d3; }
    .calendar-custom-due { background-color: rgba(0, 123, 255, 0.15); color: #007bff; border-left: 4px solid #007bff; }
    .calendar-paid { background-color: rgba(108, 117, 125, 0.15); color: #6c757d; border-left: 4px solid #6c757d; }
    .cal-day-box { border-radius: 8px; min-height: 96px; padding: 6px; margin-bottom: 4px; }
    .cal-day-today { border: 2px solid #0284c7 !important; background: #eff6ff !important; }
    .cal-day-muted { opacity: 0.4; background: #f1f5f9; border: 1px solid #e2e8f0; }
    .cal-day-normal { background: #ffffff; border: 1px solid #e2e8f0; }

    .stButton>button {
        border-radius: 8px;
        transition: all 0.2s ease;
        font-weight: 500;
        min-height: 2.75rem;
        padding: 0.5rem 1rem;
    }

    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 10px rgba(0, 201, 255, 0.25);
    }

    [data-testid="stMetricValue"] {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
    }

    @media (max-width: 768px) {
        .app-title { font-size: 1.75rem; }
        .stButton>button { min-height: 3rem; width: 100%; }
        [data-testid="column"] { min-width: 100% !important; }
    }
</style>
"""

_DARK_SURFACE = """
    html, .stApp { color-scheme: dark; }
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] .main {
        --text-color: #fafafa;
        --background-color: #0e1117;
        --secondary-background-color: #1a1d24;
        background-color: #0e1117 !important;
        color: #fafafa;
    }
    [data-testid="stHeader"] {
        background-color: rgba(14, 17, 23, 0.95) !important;
    }
    [data-testid="stSidebar"] {
        --text-color: #fafafa;
        --background-color: #0e1117;
        --secondary-background-color: #1a1d24;
        background-color: #0e1117 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
        color: #fafafa;
    }
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] span,
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] .stMarkdown,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stCaption"] {
        color: #fafafa !important;
    }
    .app-subtitle { color: #8c96a6 !important; }
    [data-testid="stAppViewContainer"] input,
    [data-testid="stAppViewContainer"] textarea,
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
        -webkit-text-fill-color: #fafafa !important;
        caret-color: #fafafa !important;
        border-color: rgba(255, 255, 255, 0.15) !important;
    }
    [data-baseweb="input"] > div,
    [data-baseweb="base-input"],
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div,
    [data-baseweb="popover"] {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
        border-color: rgba(255, 255, 255, 0.15) !important;
    }
    [data-baseweb="menu"] li,
    [data-baseweb="menu"] ul {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
    }
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] span,
    [data-testid="stCheckbox"] span {
        color: #fafafa !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #1a1d24 !important;
        border-color: rgba(255, 255, 255, 0.1) !important;
    }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] div,
    [data-testid="stAlert"] span {
        color: #fafafa !important;
    }
    [data-testid="stMetricLabel"] { color: #8c96a6 !important; }
    [data-testid="stMetricValue"] { color: #fafafa !important; }
    div[data-testid="stExpander"] details {
        background-color: rgba(255, 255, 255, 0.03) !important;
        border-color: rgba(255, 255, 255, 0.08) !important;
        color: #fafafa !important;
    }
    .stButton>button {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
    }
    .stButton>button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: none !important;
    }
    [data-testid="stSidebar"] .stButton>button {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
    }
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] div,
    [data-testid="stDataFrame"] canvas {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
    }
    [data-testid="stTable"] {
        background-color: #1a1d24 !important;
    }
    [data-testid="stTable"] table {
        color: #fafafa !important;
    }
    [data-testid="stTable"] th {
        background-color: #252830 !important;
        color: #fafafa !important;
    }
    [data-testid="stTable"] td {
        background-color: #1a1d24 !important;
        color: #fafafa !important;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px rgba(255, 255, 255, 0.08) solid;
    }
    .kpi-container {
        background: linear-gradient(145deg, rgba(23, 26, 32, 0.8) 0%, rgba(13, 15, 19, 0.9) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    }
    .kpi-label { color: #8a92a6; }
    .kpi-value { color: #ffffff; }
    .cal-day-normal { background: #1a1d24 !important; border-color: rgba(255,255,255,0.1) !important; }
    .cal-day-muted { background: #12151a !important; border-color: rgba(255,255,255,0.06) !important; }
    .cal-day-today { background: rgba(2,132,199,0.15) !important; border-color: #0284c7 !important; }
"""

_DARK_CSS = f"""
<style>
{_DARK_SURFACE}
</style>
"""

_LIGHT_SURFACE = """
    html, .stApp { color-scheme: light; }
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] .main {
        --text-color: #0f172a;
        --background-color: #f1f5f9;
        --secondary-background-color: #ffffff;
        background-color: #f1f5f9 !important;
        color: #0f172a;
    }
    [data-testid="stHeader"] {
        background-color: rgba(248, 250, 252, 0.95) !important;
    }
    [data-testid="stSidebar"] {
        --text-color: #1e293b;
        --background-color: #f8fafc;
        --secondary-background-color: #ffffff;
        background-color: #f8fafc !important;
        border-right: 1px solid rgba(15, 23, 42, 0.08);
        color: #1e293b;
    }
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] span,
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] .stMarkdown,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] [data-testid="stCaption"],
    [data-testid="stCaption"] {
        color: #1e293b !important;
    }
    .app-subtitle { color: #5c6573 !important; }
    [data-testid="stAppViewContainer"] input,
    [data-testid="stAppViewContainer"] textarea,
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea {
        background-color: #ffffff !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        caret-color: #0f172a !important;
    }
    [data-baseweb="input"] > div,
    [data-baseweb="base-input"],
    [data-baseweb="textarea"] > div {
        background-color: #ffffff !important;
        border-color: #cbd5e1 !important;
    }
    [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #0f172a !important;
    }
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] span,
    [data-testid="stCheckbox"] span {
        color: #1e293b !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border-color: #e2e8f0 !important;
    }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] div,
    [data-testid="stAlert"] span,
    [data-testid="stNotificationContentInfo"],
    [data-testid="stNotificationContentWarning"],
    [data-testid="stNotificationContentError"],
    [data-testid="stNotificationContentSuccess"] {
        color: #1e293b !important;
    }
    [data-testid="stMetricLabel"] { color: #64748b !important; }
    [data-testid="stMetricValue"] { color: #0f172a !important; }
    div[data-testid="stExpander"] details {
        background-color: #ffffff !important;
        border-color: rgba(15, 23, 42, 0.1) !important;
        color: #1e293b !important;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(15, 23, 42, 0.08);
    }
    .kpi-container {
        background: linear-gradient(145deg, #ffffff 0%, #f4f7fb 100%);
        border: 1px solid rgba(15, 23, 42, 0.08);
        box-shadow: 0 4px 15px rgba(15, 23, 42, 0.06);
    }
    .kpi-label { color: #64748b; }
    .kpi-value { color: #0f172a; }
    .stButton>button {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid rgba(15, 23, 42, 0.12) !important;
    }
    .stButton>button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: none !important;
    }
    [data-testid="stSidebar"] .stButton>button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #0f172a !important;
    }
"""

_LIGHT_CSS = f"""
<style>
{_LIGHT_SURFACE}
</style>
"""

_SYSTEM_CSS = """
<style>
    @media (prefers-color-scheme: dark) {
""" + _DARK_SURFACE + """
    }
    @media (prefers-color-scheme: light) {
""" + _LIGHT_SURFACE + """
    }
</style>
"""


def get_chart_colors(theme: str | None = None) -> dict:
    """Plotly-friendly colors for the active theme."""
    mode = theme or st.session_state.get("ui_theme", "system")
    if mode == "light":
        return {"font": "#0f172a", "paper": "rgba(0,0,0,0)", "plot": "rgba(0,0,0,0)"}
    if mode == "dark":
        return {"font": "#ffffff", "paper": "rgba(0,0,0,0)", "plot": "rgba(0,0,0,0)"}
    return {"font": "#94a3b8", "paper": "rgba(0,0,0,0)", "plot": "rgba(0,0,0,0)"}


def inject_custom_css(theme: str | None = None):
    """Inject base + theme-specific stylesheet."""
    init_theme_state()
    mode = theme or st.session_state.get("ui_theme", "system")
    st.markdown(_BASE_CSS, unsafe_allow_html=True)
    if mode == "light":
        st.markdown(_LIGHT_CSS, unsafe_allow_html=True)
    elif mode == "dark":
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
    else:
        st.markdown(_SYSTEM_CSS, unsafe_allow_html=True)
    scheme = "light" if mode == "light" else ("dark" if mode == "dark" else "light dark")
    st.markdown(
        f"<script>document.documentElement.style.colorScheme = '{scheme}';</script>",
        unsafe_allow_html=True,
    )
