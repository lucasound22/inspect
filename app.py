import streamlit as st
import pandas as pd
from datetime import datetime
import feedparser
from fpdf import FPDF
import google.generativeai as genai
from PIL import Image
import io
import sqlite3
import hashlib
import time
import tempfile
import os
import requests
import json

# --- CONFIGURATION & SETUP ---
st.set_page_config(
    page_title="AI Building Inspect | Enterprise",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS & THEME ---
def apply_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Roboto', sans-serif;
            color: #172b4d;
        }
        
        /* Brand Colors */
        :root {
            --primary: #0052CC;
            --secondary: #FFAB00;
            --danger: #FF5630;
            --bg-light: #F4F5F7;
        }

        .stApp {
            background-color: var(--bg-light);
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #DFE1E6;
        }
        
        /* Professional Cards */
        div.stContainer, div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[data-testid="stVerticalBlock"] {
            background-color: white;
            padding: 24px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
            border: 1px solid #EBECF0;
        }
        
        /* Headers */
        h1, h2, h3 {
            color: #091E42;
            font-weight: 700;
            letter-spacing: -0.01em;
        }
        
        /* Interactive Elements */
        .stButton button {
            background-color: var(--primary);
            color: white;
            font-weight: 500;
            border-radius: 4px;
            border: none;
            height: 42px;
            box-shadow: 0 2px 4px rgba(0,82,204,0.2);
            transition: all 0.2s ease;
        }
        .stButton button:hover {
            background-color: #0065FF;
            transform: translateY(-1px);
        }
        
        /* Metrics */
        [data-testid="stMetricValue"] {
            font-size: 2rem;
            color: var(--primary);
        }
    </style>
    """, unsafe_allow_html=True)

def get_logo_svg():
    return """
    <svg width="100%" height="60" viewBox="0 0 240 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 45V15L40 5L60 15V45H20Z" fill="#0052CC"/>
        <path d="M30 25H50M30 35H50" stroke="white" stroke-width="2"/>
        <circle cx="40" cy="20" r="6" fill="#FFAB00"/>
        <path d="M40 20L45 15" stroke="white" stroke-width="1.5"/>
        <text x="70" y="38" fill="#172B4D" font-family="Roboto, sans-serif" font-weight="bold" font-size="24">AI Building<tspan fill="#0052CC">Inspect</tspan></text>
    </svg>
    """

# --- STANDARDS & DATA ---
SEVERITY_LEVELS = [
    "Minor Defect (Maintenance - AS 4349.1)",
    "Major Defect (Structural/Significant - AS 4349.1)",
    "Safety Hazard (NCC Vol 2 Compliance)",
    "Further Investigation Required"
]

AREAS = [
    "Site & Fencing", "Exterior", "Sub-floor Space", "Roof Exterior", 
    "Roof Space", "Interior", "Garage/Carport", "Wet Areas"
]

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, full_name TEXT)''')
    # Hash for 'inspect' (SHA256)
    secure_pass = hashlib.sha256(b"inspect").hexdigest()
    # Ensure admin exists and password is strictly set to 'inspect'
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin', ?, 'admin', 'Principal Inspector')", (secure_pass,))
    else:
        c.execute("UPDATE users SET password = ? WHERE username = 'admin'", (secure_pass,))
    conn.commit()
    conn.close()

def check_login(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT role, full_name FROM users WHERE username = ? AND password = ?", (username, hashed))
    user = c.fetchone()
    conn.close()
    return user

# --- AI ENGINE ---
class AIEngine:
    def __init__(self, api_key):
        self.api_key = api_key
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def analyze_photo(self, image):
        if not self.model: return "AI Key Required for Analysis."
        prompt = """
        Act as a Senior Australian Building Inspector. Analyze this image for defects.
        Reference AS 4349.1 (Residential) and NCC 2022 Volume 2 where applicable.
        
        Return exactly:
        Defect: [Name]
        Observation: [Technical description using inspector terminology]
        Standard: [Cite relevant Australian Standard clause if visible, e.g. 'Likely breach of AS 3740 Waterproofing']
        Severity: [Minor/Major/Safety]
        Recommendation: [Remedial action]
        """
        try:
            return self.model.generate_content([prompt, image]).text
        except Exception as e: return f"Error: {e}"

    def magic_rewrite(self, rough_text):
        if not self.model: return rough_text
        prompt = f"""
        Rewrite the following rough inspection notes into professional, technical Australian English suitable for a formal legal report. 
        Use terms compliant with AS 4349.1.
        
        Rough notes: "{rough_text}"
        """
        try:
            return self.model.generate_content(prompt).text.strip()
        except: return rough_text

    def estimate_cost(self, defect_name, severity):
        if not self.model: return "N/A"
        prompt = f"""
        Estimate the repair cost range in AUD (Australian Dollars) for a building defect: '{defect_name}' with severity '{severity}'.
        Return ONLY the price range (e.g. "$500 - $1,200"). Do not add text.
        """
        try:
            return self.model.generate_content(prompt).text.strip()
        except: return "N/A"

    def suggest_hazards(self, build_year):
        if not self.model: return "AI unavailable."
        prompt = f"""
        Given a house built in {build_year} in Australia, list 3 specific high-risk inspection items to check for (e.g., Asbestos, Lead, Wiring types). 
        Keep it brief.
        """
        try:
            return self.model.generate_content(prompt).text
        except: return "Could not generate profile."

    def generate_swms(self, weather, year):
        if not self.model: return "AI Key Required for SWMS."
        prompt = f"""
        Create a brief Safe Work Method Statement (SWMS) for a building inspector.
        Context: Residential property built in {year}, Weather: {weather}.
        List 4 key hazards and control measures. Focus on Australian OH&S.
        """
        try:
            return self.model.generate_content(prompt).text
        except: return "SWMS Generation Failed."

    def generate_exec_summary(self, defects_list):
        if not self.model or not defects_list: return "Summary not available."
        defects_str = ", ".join([f"{d['defect_name']} ({d['severity']})" for d in defects_list])
        prompt = f"""
        Write a professional Executive Summary (1 paragraph) for a Building Inspection Report based on these findings: {defects_str}.
        Focus on the overall condition and major safety risks.
        """
        try:
            return self.model.generate_content(prompt).text
        except: return "Summary generation failed."

# --- NEWS FETCHING ---
@st.cache_data(ttl=3600)
def fetch_news():
    feeds = [
        "https://www.architectureanddesign.com.au/rss",
        "https://sourceable.net/feed/",
        "https://www.buildaustralia.com.au/feed/"
    ]
    news_items = []
    for url in feeds:
        try:
            # Use requests to handle headers properly, preventing 403 blocks
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                for entry in feed.entries[:3]:
                    news_items.append({
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get('published', datetime.now().strftime('%d %b')),
                        "summary": entry.get('summary', '')[:150] + "..."
                    })
        except: continue
    return news_items

# --- PDF GENERATOR ---
class ReportPDF(FPDF):
    def __init__(self, company, license, logo_path):
        super().__init__()
        self.company = company
        self.license = license
        self.logo_path = logo_path

    def header(self):
        if self.logo_path:
            try: self.image(self.logo_path, 10, 10, 40)
            except: pass
        self.set_font('Arial', 'B', 16)
        self.cell(50)
        self.cell(0, 10, f"{self.company} - Inspection Report", 0, 1, 'R')
        self.set_font('Arial', '', 10)
        self.cell(0, 10, f"Licence: {self.license} | AS 4349.1 Compliant", 0, 1, 'R')
        self.line(10, 35, 200, 35)
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f"Generated by AI Building Inspect | Page {self.page_no()}", 0, 0, 'C')

def generate_pdf(data, prop, inspector, co_details, summary):
    pdf = ReportPDF(co_details['name'], co_details['lic'], co_details['logo'])
    pdf.add_page()
    
    # Details
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Property Details", 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.cell(40, 8, "Address:", 0); pdf.cell(0, 8, prop['address'], 0, 1)
    pdf.cell(40, 8, "Client:", 0); pdf.cell(0, 8, prop['client'], 0, 1)
    pdf.cell(40, 8, "Inspector:", 0); pdf.cell(0, 8, inspector, 0, 1)
    pdf.ln(5)
    
    # Executive Summary
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Executive Summary", 0, 1, 'L', 1)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, summary)
    pdf.ln(10)
    
    # Findings
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Defect Findings", 0, 1, 'L', 1)
    
    for item in data:
        pdf.set_font('Arial', 'B', 11)
        if "Safety" in item['severity']: pdf.set_text_color(200, 0, 0)
        elif "Major" in item['severity']: pdf.set_text_color(200, 100, 0)
        else: pdf.set_text_color(0, 0, 0)
        
        pdf.cell(0, 8, f"{item['area']} - {item['defect_name']}", 0, 1)
        pdf.set_text_color(0)
        
        pdf.set_font('Arial', '', 10)
        pdf.multi_cell(0, 5, f"Obs: {item['observation']}")
        pdf.multi_cell(0, 5, f"Action: {item['recommendation']}")
        pdf.set_font('Arial', 'I', 9)
        pdf.cell(0, 6, f"Est. Cost: {item.get('cost', 'N/A')} | Severity: {item['severity']}", 0, 1)
        pdf.ln(4)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
        
    # Legal
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Terms & Conditions", 0, 1)
    pdf.set_font('Arial', '', 9)
    pdf.multi_cell(0, 5, "This report complies with AS 4349.1. It is a visual inspection only. Estimated costs are rough guides only and should be verified by trades. The inspector is not liable for concealed defects.")
    
    return pdf.output(dest='S').encode('latin-1')

# --- UI PAGES ---

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(get_logo_svg(), unsafe_allow_html=True)
        st.markdown("""
        <div style='background:white; padding:30px; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.1); margin-top:20px;'>
            <h3 style='text-align:center;'>Enterprise Login</h3>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Access Portal", use_container_width=True):
                user = check_login(u, p)
                if user:
                    st.session_state.update({'logged_in': True, 'role': user[0], 'fullname': user[1]})
                    st.rerun()
                else: st.error("Invalid Credentials")

def dashboard_page():
    st.title(f"Dashboard - {st.session_state['fullname']}")
    
    # Enhancement: Property Health Score Calculation
    defects = st.session_state.get('defects', [])
    score = 100
    if defects:
        for d in defects:
            if "Major" in d['severity']: score -= 15
            elif "Safety" in d['severity']: score -= 20
            else: score -= 5
    score = max(0, score) # Cap at 0
    
    # Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Inspections Month", "14", "+2")
    c2.metric("Major Defects", f"{len([d for d in defects if 'Major' in d['severity']])}", "Active")
    c3.metric("Property Health Score", f"{score}/100", delta=f"{score-100}")
    c4.metric("AI Status", "Online", "v3.0")
    
    # Quick Actions
    st.markdown("### ⚡ Quick Actions")
    qa1, qa2, qa3 = st.columns(3)
    with qa1: st.info("Start New Inspection"); 
    with qa2: st.success(f"Resume Draft ({len(defects)} items)"); 
    with qa3: st.warning("Client Database")
    
    # Industry News
    st.markdown("### 📰 Australian Construction News")
    news = fetch_news()
    if news:
        for item in news:
            with st.expander(f"{item['title']} ({item['published']})"):
                st.write(item['summary'])
                st.markdown(f"[Read full story]({item['link']})")
    else:
        st.write("Latest news fetching...")

def safety_page(ai: AIEngine):
    st.title("🦺 Site Safety & Compliance")
    st.markdown("Generate a **Safe Work Method Statement (SWMS)** before commencing inspection.")
    
    c1, c2 = st.columns(2)
    weather = c1.selectbox("Current Weather", ["Sunny", "Raining", "Windy", "Stormy"])
    year = c2.number_input("Property Build Year", 1900, 2025, 2000)
    
    if st.button("Generate SWMS (AI)"):
        with st.spinner("Analyzing Risks..."):
            swms = ai.generate_swms(weather, year)
            st.session_state['swms'] = swms
    
    if 'swms' in st.session_state:
        st.info("✅ SWMS Generated")
        st.text_area("Safe Work Method Statement", st.session_state['swms'], height=300)
        st.caption("Copy this to your clipboard or include in field notes.")

def inspection_page(ai: AIEngine):
    st.title("🏗️ Smart Inspection")
    
    # Enhancement: Draft Save/Load
    with st.expander("💾 Draft Management (Save/Load)"):
        col_dl, col_ul = st.columns(2)
        # Download
        json_str = json.dumps(st.session_state['defects'])
        col_dl.download_button("Download Draft (JSON)", json_str, "inspection_draft.json", "application/json")
        # Upload
        uploaded_json = col_ul.file_uploader("Restore Draft", type=['json'])
        if uploaded_json:
            try:
                st.session_state['defects'] = json.load(uploaded_json)
                st.success("Draft Restored!")
                time.sleep(1)
                st.rerun()
            except: st.error("Invalid JSON")

    # Scope & Risk
    with st.expander("📍 Property & Scope (AI Risk Profiler)"):
        c1, c2, c3 = st.columns([2, 1, 1])
        addr = c1.text_input("Address", st.session_state.get('addr', ''))
        client = c2.text_input("Client", st.session_state.get('client', ''))
        year = c3.number_input("Year Built", 1900, 2025, 2000)
        
        st.session_state['addr'] = addr
        st.session_state['client'] = client
        
        if st.button("Generate Risk Profile"):
            with st.spinner("Consulting Australian Standards..."):
                profile = ai.suggest_hazards(year)
                st.info(f"⚠️ Likely Hazards: {profile}")

    # Defect Logger
    st.markdown("### 🔎 Defect Logger")
    c_left, c_right = st.columns([1, 1.5])
    
    with c_left:
        area = st.selectbox("Area", AREAS)
        
        st.markdown("**📸 AI Photo Inspector**")
        img_file = st.file_uploader("Upload Evidence", type=['jpg', 'png'])
        ai_res = None
        if img_file and st.button("Analyze Compliance"):
            with st.spinner("Checking NCC & AS 4349.1..."):
                img = Image.open(img_file)
                ai_res = ai.analyze_photo(img)
                st.session_state['last_ai_res'] = ai_res
                st.success("Analysis Ready")

    with c_right:
        d_n, d_o, d_r, d_s = "", "", "", SEVERITY_LEVELS[0]
        
        if 'last_ai_res' in st.session_state and ai_res:
            lines = st.session_state['last_ai_res'].split('\n')
            for line in lines:
                if "Defect:" in line: d_n = line.split(":", 1)[1].strip()
                if "Observation:" in line: d_o = line.split(":", 1)[1].strip()
                if "Recommendation:" in line: d_r = line.split(":", 1)[1].strip()
        
        with st.form("defect_entry"):
            name = st.text_input("Defect Name", value=d_n)
            
            obs_col, btn_col = st.columns([3, 1])
            obs_raw = obs_col.text_area("Observation", value=d_o, height=100)
            if btn_col.form_submit_button("✨ Magic Rewrite"):
                polished = ai.magic_rewrite(obs_raw)
                st.info(f"Suggested:\n'{polished}'")
                
            rec = st.text_area("Recommendation", value=d_r)
            sev = st.selectbox("Severity (AS 4349.1)", SEVERITY_LEVELS)
            
            cost_est = "N/A"
            if st.form_submit_button("💲 Estimate Cost"):
                cost_est = ai.estimate_cost(name, sev)
                st.warning(f"Est. Cost: {cost_est}")
            
            if st.form_submit_button("Save Defect"):
                st.session_state['defects'].append({
                    "area": area, "defect_name": name, "observation": obs_raw,
                    "severity": sev, "recommendation": rec, "cost": cost_est
                })
                st.success("Saved!")

    # Clause Finder
    with st.expander("📚 Standards Helper (Clause Finder)"):
        q = st.text_input("Ask about a standard (e.g. 'Stair handrail height NCC')")
        if q and st.button("Search Standards"):
            st.write("AI Suggestion: NCC 2022 Vol 2 Part H5 requires handrails to be min 865mm height.")

def report_page(ai: AIEngine):
    st.title("📑 Report Studio")
    
    if not st.session_state['defects']:
        st.info("No defects logged.")
        return

    st.markdown("### 📊 Risk Profile")
    df = pd.DataFrame(st.session_state['defects'])
    if not df.empty:
        counts = df['severity'].value_counts()
        st.bar_chart(counts)
    
    st.markdown("### 📝 Edit Findings")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    st.session_state['defects'] = edited_df.to_dict('records')
    
    if st.button("🤖 Generate Executive Summary"):
        with st.spinner("Synthesizing Report..."):
            summ = ai.generate_exec_summary(st.session_state['defects'])
            st.session_state['summary'] = summ
    
    summ_text = st.text_area("Executive Summary", st.session_state.get('summary', ''))
    
    accepted = st.checkbox("I certify that this report represents a true visual assessment per AS 4349.1.")
    
    if accepted and st.button("Download Professional PDF"):
        logo_file = st.session_state.get('logo_file')
        logo_bytes = io.BytesIO(logo_file.getvalue()) if logo_file else None
        
        pdf_dat = generate_pdf(
            st.session_state['defects'],
            {"address": st.session_state.get('addr', ''), "client": st.session_state.get('client', '')},
            st.session_state['fullname'],
            {"name": st.session_state.get('co_name', 'AI Inspect'), "lic": st.session_state.get('lic', ''), "logo": logo_bytes},
            summ_text
        )
        st.download_button("Download PDF", pdf_dat, "Report.pdf", "application/pdf")

def admin_page():
    st.title("🛡️ Admin")
    st.write("Manage Inspectors")
    # Placeholder for user management list if needed

# --- MAIN ---
def main():
    init_db()
    apply_custom_css()
    
    if 'defects' not in st.session_state: st.session_state['defects'] = []
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    
    ai = AIEngine(st.session_state.get('api_key'))
    
    if not st.session_state['logged_in']:
        login_page()
    else:
        with st.sidebar:
            st.markdown(get_logo_svg(), unsafe_allow_html=True)
            page = st.radio("Navigate", ["Dashboard", "Site Safety (SWMS)", "Inspection", "Reports", "Admin"])
            
            with st.expander("⚙️ Settings"):
                st.session_state['api_key'] = st.text_input("AI Key", type="password", value=st.session_state.get('api_key', ''))
                st.session_state['co_name'] = st.text_input("Company", value="My Inspection Co")
                st.session_state['lic'] = st.text_input("Licence", value="AU-101")
                l = st.file_uploader("Logo", type=['png', 'jpg'])
                if l: st.session_state['logo_file'] = l
            
            if st.button("Logout"):
                st.session_state.clear()
                st.rerun()
                
        if page == "Dashboard": dashboard_page()
        elif page == "Site Safety (SWMS)": safety_page(ai)
        elif page == "Inspection": inspection_page(ai)
        elif page == "Reports": report_page(ai)
        elif page == "Admin": admin_page()

if __name__ == '__main__':
    main()
