import streamlit as st

def inject_custom_css():
    """
    Injects custom CSS to style the Streamlit application with a premium, modern fintech look.
    Includes glassmorphism cards, metric styles, alert tags, and sidebar customization.
    """
    css = """
    <style>
        /* Import Outfit Google Font */
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        /* Title styling */
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
            color: #8C96A6;
            font-size: 1rem;
            margin-top: 0;
            margin-bottom: 2rem;
        }

        /* Glassmorphism Cards */
        .glass-card {
            background: rgba(255, 255, 255, 0.04);
            border-radius: 16px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 1px rgba(255, 255, 255, 0.08) solid;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        
        /* KPI Metrics Cards */
        .kpi-container {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            background: linear-gradient(145deg, rgba(23, 26, 32, 0.8) 0%, rgba(13, 15, 19, 0.9) 100%);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 1.25rem;
            min-height: 120px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        
        .kpi-container:hover {
            transform: translateY(-2px);
            border-color: rgba(0, 201, 255, 0.4);
        }
        
        .kpi-label {
            color: #8A92A6;
            font-size: 0.85rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .kpi-value {
            color: #FFFFFF;
            font-size: 1.6rem;
            font-weight: 700;
            margin-top: 0.5rem;
        }
        
        .kpi-delta {
            font-size: 0.8rem;
            font-weight: 500;
            margin-top: 0.4rem;
        }
        
        .kpi-delta.up {
            color: #00E676;
        }
        
        .kpi-delta.down {
            color: #FF5252;
        }
        
        .kpi-delta.neutral {
            color: #9E9E9E;
        }

        /* Financial Health Indicators */
        .status-pill {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            text-align: center;
        }
        
        .status-pill.critical {
            background-color: rgba(255, 82, 82, 0.15);
            color: #FF5252;
            border: 1px solid rgba(255, 82, 82, 0.3);
        }
        
        .status-pill.poor {
            background-color: rgba(255, 177, 66, 0.15);
            color: #FFB142;
            border: 1px solid rgba(255, 177, 66, 0.3);
        }
        
        .status-pill.good {
            background-color: rgba(0, 201, 255, 0.15);
            color: #00C9FF;
            border: 1px solid rgba(0, 201, 255, 0.3);
        }
        
        .status-pill.excellent {
            background-color: rgba(46, 213, 115, 0.15);
            color: #2ED573;
            border: 1px solid rgba(46, 213, 115, 0.3);
        }
        
        .status-pill.exceptional {
            background-color: rgba(146, 254, 157, 0.15);
            color: #92FE9D;
            border: 1px solid rgba(146, 254, 157, 0.3);
        }
        
        /* Financial Calendar Custom styling */
        .calendar-cell {
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 5px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        
        .calendar-income {
            background-color: rgba(46, 213, 115, 0.15);
            color: #2ed573;
            border-left: 4px solid #2ed573;
        }
        
        .calendar-bill {
            background-color: rgba(255, 82, 82, 0.15);
            color: #ff5252;
            border-left: 4px solid #ff5252;
        }
        
        .calendar-savings {
            background-color: rgba(0, 201, 255, 0.15);
            color: #00c9ff;
            border-left: 4px solid #00c9ff;
        }
        
        .calendar-debt {
            background-color: rgba(255, 177, 66, 0.15);
            color: #ffb142;
            border-left: 4px solid #ffb142;
        }
        
        .calendar-goal {
            background-color: rgba(146, 254, 157, 0.15);
            color: #92fe9d;
            border-left: 4px solid #92fe9d;
        }
        
        .calendar-subscription {
            background-color: rgba(186, 85, 211, 0.15);
            color: #ba55d3;
            border-left: 4px solid #ba55d3;
        }

        /* Button micro-interactions */
        .stButton>button {
            border-radius: 8px;
            transition: all 0.2s ease;
            font-weight: 500;
        }
        
        .stButton>button:hover {
            transform: scale(1.02);
            box-shadow: 0 4px 10px rgba(0, 201, 255, 0.25);
        }

        /* Sidebar Styling overrides */
        [data-testid="stSidebar"] {
            background-color: #0E1117;
            border-right: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        /* Metric widget styling */
        [data-testid="stMetricValue"] {
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
        }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
