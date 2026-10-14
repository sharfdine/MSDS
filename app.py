"""
Automated Continuous-Quality-Monitoring Dashboard for Category-I Hospitals
Punjab Healthcare Commission (PHC) Minimum Service Delivery Standards (MSDS)
Main Streamlit Application
"""

import streamlit as st
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Streamlit Page Configuration
st.set_page_config(
    page_title="PHC MSDS Category-I Quality Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics and clean medical dashboard typography
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Main container padding */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
        padding-left: 2.5rem;
        padding-right: 2.5rem;
    }
    
    /* Metrics styling */
    [data-testid="stMetricValue"] {
        font-size: 1.7rem !important;
        font-weight: 800 !important;
        color: #0F172A;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: #64748B !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        color: #F8FAFC;
    }
    section[data-testid="stSidebar"] .stRadio label {
        color: #E2E8F0 !important;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    
    /* DataFrame styling */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #E2E8F0;
    }
</style>
""", unsafe_allow_html=True)

# Import Core and Views
from core.database import db
from core.hims_pipeline import hims_pipeline
from views.executive_overview import render_executive_overview
from views.kpi_monitor import render_kpi_monitor
from views.indicator_detail import render_indicator_detail
from views.alert_center import render_alert_center
from views.capa_tracker import render_capa_tracker
from views.report_generator import render_report_generator
from views.hims_integration import render_hims_integration
from views.config_audit import render_config_audit

# Initialize synthetic history if first run
hims_pipeline.initialize_synthetic_history(days=90)

# Session state initialization
if "current_role" not in st.session_state:
    st.session_state["current_role"] = "Quality Director / CQI Lead"
if "current_user" not in st.session_state:
    st.session_state["current_user"] = "Dr. Ayesha Malik"

# Sidebar Navigation & Context
with st.sidebar:
    st.markdown("""
        <div style="padding: 10px 0 16px 0; border-bottom: 1px solid #334155; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 2rem;">🏥</span>
                <div>
                    <h3 style="margin: 0; color: #FFFFFF; font-size: 1.1rem; font-weight: 800;">MSDS Quality Monitor</h3>
                    <span style="color: #38BDF8; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em;">
                        PUNJAB HEALTHCARE COMMISSION
                    </span>
                </div>
            </div>
            <div style="color: #94A3B8; font-size: 0.76rem; margin-top: 8px;">
                Category-I Tertiary Hospital Standard (30 Standards, 162 Indicators)
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Active User Persona Pill
    st.markdown(f"""
        <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; margin-bottom: 20px;">
            <div style="font-size: 0.72rem; color: #94A3B8; font-weight: 700; text-transform: uppercase;">ACTIVE PERSONA</div>
            <div style="font-size: 0.88rem; font-weight: 700; color: #F8FAFC;">{st.session_state['current_user']}</div>
            <div style="font-size: 0.76rem; color: #38BDF8;">{st.session_state['current_role']}</div>
        </div>
    """, unsafe_allow_html=True)

    # Main Navigation Radio
    nav_selection = st.radio(
        "Navigation",
        [
            "Executive Overview",
            "KPI Monitor & Trends",
            "Indicator Detail & SPC",
            "Alert Center & Early Warning",
            "CAPA Action Tracker",
            "Monthly CQI Committee Report",
            "HIMS Ingestion Pipeline",
            "Rules Config & Audit Trail"
        ],
        label_visibility="collapsed"
    )

    st.markdown("<hr style='border: none; border-top: 1px solid #334155; margin: 24px 0 16px 0;'>", unsafe_allow_html=True)

    # System Diagnostics Pill
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM alerts WHERE status = 'Open'")
    active_alerts_cnt = cur.fetchone()["cnt"]
    conn.close()

    st.markdown(f"""
        <div style="font-size: 0.76rem; color: #94A3B8;">
            <div>⚡ <b>HIMS ETL:</b> <span style="color: #4ADE80;">Automated / 90 Days</span></div>
            <div>🚨 <b>Active Alerts:</b> <span style="color: {'#F87171' if active_alerts_cnt > 0 else '#4ADE80'}; font-weight: 700;">{active_alerts_cnt} Pending</span></div>
            <div>🏛️ <b>MSDS Standard:</b> Cat-I v2.0 (2024.1)</div>
            <div>🔒 <b>Scoring Mode:</b> Deterministic Engine</div>
        </div>
    """, unsafe_allow_html=True)

# Routing Views
if nav_selection == "Executive Overview":
    render_executive_overview()
elif nav_selection == "KPI Monitor & Trends":
    render_kpi_monitor()
elif nav_selection == "Indicator Detail & SPC":
    render_indicator_detail()
elif nav_selection == "Alert Center & Early Warning":
    render_alert_center()
elif nav_selection == "CAPA Action Tracker":
    render_capa_tracker()
elif nav_selection == "Monthly CQI Committee Report":
    render_report_generator()
elif nav_selection == "HIMS Ingestion Pipeline":
    render_hims_integration()
elif nav_selection == "Rules Config & Audit Trail":
    render_config_audit()
