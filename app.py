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
import requests
import json
import base64

# --- CONFIGURATION & SETUP ---
st.set_page_config(
    page_title="SiteVision AI | Enterprise",
    page_icon="👁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- BRANDING & CSS ---
def apply_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #0F172A;
        }
        
        :root {
            --primary: #0F172A; /* Slate 900 - Brand Dark */
            --accent: #3B82F6;  /* Blue 500 - Brand Accent */
            --bg: #F8FAFC;      /* Slate 50 - Background */
            --border: #E2E8F0;  /* Slate 200 */
        }

        .stApp {
            background-color: var(--bg);
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid var(--border);
        }
        
        /* Card / Container Styling */
        div.stContainer, div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[data-testid="stVerticalBlock"] {
            background-color: white;
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            border: 1px solid var(--border);
        }
        
        /* Typography */
        h1, h2, h3 {
            color: var(--primary);
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        
        /* Buttons */
        .stButton button {
            background-color: var(--accent);
            color: white;
            font-weight: 600;
            border-radius: 6px;
            border: none;
            height: 44px;
            transition: all 0.2s ease;
        }
        .stButton button:hover {
            background-color: #2563EB;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }

        /* Input Fields */
        .stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea, .stNumberInput input {
            border-radius: 6px;
            border: 1px solid #CBD5E1;
            padding-left: 10px;
        }
        
        /* Hover Zoom Effect for Images */
        .hover-zoom {
            transition: transform 0.3s ease;
            border-radius: 8px;
            cursor: zoom-in;
            border: 1px solid #E2E8F0;
        }
        .hover-zoom:hover {
            transform: scale(1.5);
            z-index: 1000;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }
        
        /* Custom Header Icons */
        .header-icon {
            vertical-align: middle;
            margin-right: 10px;
            width: 28px;
            height: 28px;
        }
    </style>
    """, unsafe_allow_html=True)

def get_logo_svg():
    # Cleaned SVG without comments to prevent rendering errors
    return """
    <svg width="100%" height="60" viewBox="0 0 250 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="10" y="10" width="40" height="40" rx="12" fill="#0F172A"/>
        <path d="M30 20C35.5228 20 40 24.4772 40 30C40 35.5228 35.5228 40 30 40C24.4772 40 20 35.5228 20 30C20 24.4772 24.4772 20 30 20Z" stroke="#3B82F6" stroke-width="3"/>
        <circle cx="30" cy="30" r="4" fill="#3B82F6"/>
        <text x="65" y="38" fill="#0F172A" font-family="Inter, sans-serif" font-weight="bold" font-size="24" letter-spacing="-1">SiteVision <tspan fill="#3B82F6">AI</tspan></text>
    </svg>
    """

# Helper to render styled headers
def section_header(text, icon_path):
    # Using simple SVG paths for section icons to ensure consistency
    st.markdown(f"""
    <div style="display: flex; align-items: center; margin-bottom: 15px; border-bottom: 2px solid #F1F5F9; padding-bottom: 10px;">
        <h3 style="margin: 0; color: #0F172A;">{text}</h3>
    </div>
    """, unsafe_allow_html=True)

# --- CONSTANTS ---
SEVERITY_LEVELS = [
    "Minor Defect (Maintenance - AS 4349.1)",
    "Major Defect (Structural/Significant - AS 4349.1)",
    "Safety Hazard (NCC Vol 2 Compliance)",
    "Further Investigation Required"
]

AREAS = [
    "Site & Fencing", "Exterior Walls", "Sub-floor Space", "Roof Exterior", 
    "Roof Space", "Interior", "Garage/Carport", "Wet Areas", "Outbuildings"
]

# --- DATABASE MANAGEMENT ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, full_name TEXT)''')
    secure_pass = hashlib.sha256(b"inspect").hexdigest()
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin', ?, 'admin', 'System Administrator')", (secure_pass,))
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

def create_user(username, password, role, full_name):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (username, hashed, role, full_name))
        conn.commit()
        conn.close()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."

def remove_user(username):
    if username == 'admin': return False, "Cannot delete Root Admin."
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True, "User deleted."

def get_all_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT username, role, full_name FROM users", conn)
    conn.close()
    return df

# --- AI ENGINE ---
class AIEngine:
    def __init__(self, api_key):
        self.api_key = api_key
        self.model = None
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analyze_photo(self, image):
        if not self.model: return None
        prompt = """
        Act as a Licensed Australian Building Inspector. Analyze this defect image.
        Reference specific clauses from AS 4349.1 and NCC 2022 where possible.
        Format output exactly as:
        Defect: [Name]
        Observation: [Technical description]
        Standard: [Standard Ref]
        Severity: [Minor/Major/Safety]
        Recommendation: [Rectification advice]
        """
        try:
            return self.model.generate_content([prompt, image]).text
        except: return "AI Error: Analysis failed."

    def magic_rewrite(self, text):
        if not self.model: return text
        prompt = f"Rewrite these inspection notes into formal Australian Standards compliant report language: '{text}'"
        try:
            return self.model.generate_content(prompt).text.strip()
        except: return text

    def estimate_cost(self, defect, severity):
        if not self.model: return "N/A"
        prompt = f"Provide a repair cost range in AUD for '{defect}' ({severity}) in Australia. Return ONLY range string (e.g. '$500 - $1,000')."
        try:
            return self.model.generate_content(prompt).text.strip()
        except: return "N/A"

    def suggest_hazards(self, year):
        if not self.model: return "N/A"
        prompt = f"List 3 likely building hazards for a house built in {year} in Australia (e.g. Asbestos, Wiring). Brief list."
        try:
            return self.model.generate_content(prompt).text
        except: return "N/A"
        
    def generate_swms_content(self, weather, year):
        if not self.model: return None
        prompt = f"""
        Generate a Safe Work Method Statement (SWMS) Table for inspecting a property built in {year} during {weather} conditions.
        Return strictly a JSON list of objects with keys: "activity", "hazard", "risk_level", "control".
        Example: [{{"activity": "Roof Access", "hazard": "Falls", "risk_level": "High", "control": "Use harness"}}]
        Make it specific to Australian OH&S.
        """
        try:
            txt = self.model.generate_content(prompt).text
            # Clean markdown
            txt = txt.replace('```json', '').replace('```', '')
            return json.loads(txt)
        except: return []

    def generate_exec_summary(self, defects):
        if not self.model: return ""
        d_list = ", ".join([f"{d['defect_name']} ({d['severity']})" for d in defects])
        prompt = f"Write a professional Executive Summary for a building report with these defects: {d_list}. Focus on safety and structural integrity."
        try:
            return self.model.generate_content(prompt).text
        except: return ""

# --- PDF ENGINES ---
class ReportPDF(FPDF):
    def __init__(self, company, license, logo_path):
        super().__init__()
        self.company = company
        self.license = license
        self.logo_path = logo_path

    def header(self):
        if self.logo_path:
            try: self.image(self.logo_path, 10, 8, 35)
            except: pass
        self.set_font('Arial', 'B', 16)
        self.cell(45)
        self.cell(0, 10, f"{self.company} - Inspection Report", 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(0, 10, f"Licence: {self.license} | Compliant with AS 4349.1", 0, 1, 'R')
        self.ln(15)
        self.line(10, 30, 200, 30)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f"Powered by SiteVision AI | Page {self.page_no()}", 0, 0, 'C')

class SWMSPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, "Safe Work Method Statement (SWMS)", 0, 1, 'C')
        self.ln(10)

def generate_pdf_report(data, prop, inspector, co_details, summary):
    pdf = ReportPDF(co_details['name'], co_details['lic'], co_details['logo'])
    pdf.add_page()
    
    # Property Info
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Property Overview", 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.cell(40, 7, "Address:", 0); pdf.cell(0, 7, prop['address'], 0, 1)
    pdf.cell(40, 7, "Client:", 0); pdf.cell(0, 7, prop['client'], 0, 1)
    pdf.cell(40, 7, "Inspector:", 0); pdf.cell(0, 7, inspector, 0, 1)
    pdf.ln(5)
    
    # Executive Summary
    pdf.set_fill_color(245, 247, 250)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "  Executive Summary", 0, 1, 'L', 1)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, summary)
    pdf.ln(8)
    
    # Findings
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "  Defect Register", 0, 1, 'L', 1)
    
    for item in data:
        pdf.set_font('Arial', 'B', 11)
        if "Safety" in item['severity']: pdf.set_text_color(220, 38, 38)
        elif "Major" in item['severity']: pdf.set_text_color(234, 88, 12)
        else: pdf.set_text_color(0, 82, 204)
        
        pdf.cell(0, 8, f"{item['area']} | {item['defect_name']}", 0, 1)
        pdf.set_text_color(0)
        
        pdf.set_font('Arial', '', 10)
        pdf.multi_cell(0, 5, f"Obs: {item['observation']}")
        pdf.multi_cell(0, 5, f"Rectification: {item['recommendation']}")
        
        pdf.set_font('Arial', 'I', 9)
        pdf.cell(0, 6, f"Est. Cost: {item.get('cost', 'N/A')} | {item['severity']}", 0, 1)
        
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
        
    return pdf.output(dest='S').encode('latin-1')

def generate_pdf_swms(risks, prop_addr, inspector):
    pdf = SWMSPDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 10)
    
    pdf.cell(0, 8, f"Site: {prop_addr}", 0, 1)
    pdf.cell(0, 8, f"Inspector: {inspector}", 0, 1)
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
    pdf.ln(10)
    
    # Headers
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(50, 10, "Activity", 1, 0, 'L', 1)
    pdf.cell(50, 10, "Hazard", 1, 0, 'L', 1)
    pdf.cell(30, 10, "Risk", 1, 0, 'L', 1)
    pdf.cell(60, 10, "Control Measure", 1, 1, 'L', 1)
    
    pdf.set_font('Arial', '', 9)
    for r in risks:
        # Simple multiline handling for cells
        x = pdf.get_x()
        y = pdf.get_y()
        max_h = 20 # fixed height for simplicity in demo
        
        pdf.cell(50, max_h, r.get('activity',''), 1)
        pdf.cell(50, max_h, r.get('hazard',''), 1)
        pdf.cell(30, max_h, r.get('risk_level',''), 1)
        pdf.multi_cell(60, max_h, r.get('control',''), 1)
        # Reset position if multicell breaks flow (simple grid logic)
        pdf.set_xy(x, y + max_h) 
        
    pdf.ln(10)
    pdf.cell(0, 10, "I confirm I have read and understood this SWMS.", 0, 1)
    pdf.cell(0, 10, "Signature: __________________________", 0, 1)
    
    return pdf.output(dest='S').encode('latin-1')

# --- NEWS ENGINE ---
@st.cache_data(ttl=3600)
def fetch_news():
    feeds = [
        "https://www.architectureanddesign.com.au/rss",
        "https://sourceable.net/feed/"
    ]
    items = []
    for url in feeds:
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                for entry in feed.entries[:2]:
                    items.append({
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get('published', 'Recent'),
                        "summary": entry.get('summary', '')[:140] + "..."
                    })
        except: continue
    return items

# --- UI PAGES ---

def login_page():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(get_logo_svg(), unsafe_allow_html=True)
        st.markdown("""
        <div style='background:white; padding:40px; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.05); margin-top:20px; border:1px solid #F1F5F9;'>
            <h3 style='text-align:center; margin-bottom:20px; color:#0F172A;'>Inspector Portal</h3>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            u = st.text_input("Username", help="Enter your registered username")
            p = st.text_input("Password", type="password", help="Case sensitive")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Secure Login", use_container_width=True):
                user = check_login(u, p)
                if user:
                    st.session_state.update({
                        'logged_in': True, 
                        'role': user[0], 
                        'fullname': user[1],
                        'page': 'New Inspection'
                    })
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

def admin_page():
    section_header("Admin Console", "shield")
    
    tab1, tab2 = st.tabs(["👥 User Management", "➕ Add Inspector"])
    
    with tab1:
        st.subheader("Current Users")
        users = get_all_users()
        st.dataframe(users, column_config={"username": "Username", "role": "Role", "full_name": "Full Name"}, use_container_width=True, hide_index=True)
        
        st.markdown("### User Actions")
        c1, c2 = st.columns([3, 1])
        user_to_del = c1.selectbox("Select User to Remove", users['username'].tolist())
        if c2.button("🗑️ Delete User", use_container_width=True):
            if user_to_del == st.session_state['username']: st.error("You cannot delete yourself.")
            else:
                success, msg = remove_user(user_to_del)
                if success: st.success(msg); time.sleep(1); st.rerun()
                else: st.error(msg)
                
    with tab2:
        st.subheader("Register New Inspector")
        with st.form("add_user_form"):
            c1, c2 = st.columns(2)
            new_user = c1.text_input("Username", help="Unique identifier")
            new_pass = c2.text_input("Password", type="password")
            new_name = st.text_input("Full Name")
            new_role = st.selectbox("Role", ["Inspector", "Admin"])
            
            if st.form_submit_button("Create Account"):
                if new_user and new_pass:
                    success, msg = create_user(new_user, new_pass, new_role, new_name)
                    if success: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
                else: st.warning("All fields are required.")

def safety_page(ai: AIEngine):
    section_header("Site Safety (SWMS)", "helmet")
    st.markdown("Create a **Safe Work Method Statement** before starting inspection.")
    
    if 'swms_data' not in st.session_state: st.session_state['swms_data'] = []
    
    with st.container():
        c1, c2 = st.columns(2)
        weather = c1.selectbox("Weather Conditions", ["Sunny", "Raining", "Windy", "Stormy", "Extreme Heat"], help="Affects roof access risks")
        year = c2.number_input("Property Build Year", 1900, 2025, 2000, help="Determines asbestos/lead risk")
        
        if st.button("Generate SWMS (AI)"):
            with st.spinner("Identifying Hazards..."):
                risks = ai.generate_swms_content(weather, year)
                if risks:
                    st.session_state['swms_data'] = risks
                    st.success("Risk Assessment Generated")
                else:
                    st.error("AI service unavailable. Please enter manually.")

    if st.session_state['swms_data']:
        st.subheader("Risk Register")
        # Editable Dataframe
        edited_swms = st.data_editor(
            st.session_state['swms_data'], 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "risk_level": st.column_config.SelectboxColumn("Risk", options=["Low", "Medium", "High", "Critical"])
            }
        )
        st.session_state['swms_data'] = edited_swms
        
        if st.button("📄 Download SWMS PDF"):
            pdf_bytes = generate_pdf_swms(
                st.session_state['swms_data'], 
                st.session_state.get('addr', 'Site Not Specified'), 
                st.session_state['fullname']
            )
            st.download_button("Click to Download", pdf_bytes, "SWMS.pdf", "application/pdf")

def inspection_page(ai: AIEngine):
    section_header("New Inspection", "clipboard")
    
    # 1. Save/Load Draft (Functional)
    with st.expander("💾 Session Management (Save/Restore)", expanded=False):
        c1, c2 = st.columns(2)
        current_data = json.dumps(st.session_state['defects'])
        c1.download_button("Download Progress (JSON)", current_data, "site_draft.json", "application/json", help="Save your work to a file")
        
        uploaded_json = c2.file_uploader("Restore Progress", type=['json'], help="Upload a previously saved JSON file")
        if uploaded_json:
            try:
                st.session_state['defects'] = json.load(uploaded_json)
                st.success("Session Restored!")
                time.sleep(0.5)
                st.rerun()
            except: st.error("Invalid File")

    # 2. Scope
    with st.container():
        st.subheader("Property Details")
        c1, c2, c3 = st.columns([2, 1, 1])
        addr = c1.text_input("Address", st.session_state.get('addr', ''), help="Full street address")
        client = c2.text_input("Client", st.session_state.get('client', ''), help="Name for the report")
        year = c3.number_input("Year Built", 1900, 2025, 2000, help="Used for AI risk profiling")
        
        st.session_state['addr'] = addr
        st.session_state['client'] = client

        if year and st.button("Generate Risk Profile (AI)"):
            with st.spinner("Analyzing Build Era..."):
                risk = ai.suggest_hazards(year)
                st.info(f"⚠️ Likely Era Hazards: {risk}")

    st.markdown("<br>", unsafe_allow_html=True)

    # 3. Defect Logging
    col_main, col_sidebar = st.columns([1.5, 1])
    
    with col_main:
        section_header("Defect Entry", "camera")
        with st.container():
            area = st.selectbox("Area Inspected", AREAS, help="Select the zone of the house")
            
            # AI Camera with Hover Preview
            st.markdown("**📸 Vision AI & Evidence**")
            img_file = st.file_uploader("Upload Evidence", type=['jpg', 'png'], help="Upload clear photos of the defect")
            
            ai_data = None
            if img_file:
                # Hover Preview Feature
                img_bytes = img_file.getvalue()
                b64_img = base64.b64encode(img_bytes).decode()
                st.markdown(f"""
                <div style="margin-bottom:10px;">
                    <img src="data:image/png;base64,{b64_img}" class="hover-zoom" width="150" alt="Preview">
                    <p style="font-size:12px; color:#64748B;"><i>Hover to zoom</i></p>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("Analyze Image (AI)"):
                    with st.spinner("Scanning..."):
                        ai_data = ai.analyze_photo(Image.open(img_file))
                        st.session_state['temp_ai'] = ai_data
                        st.success("Analysis Complete")

            # Form Pre-fill
            d_def, d_obs, d_rec = "", "", ""
            if 'temp_ai' in st.session_state and st.session_state['temp_ai']:
                raw = st.session_state['temp_ai']
                if "Defect:" in raw: d_def = raw.split("Defect:", 1)[1].split("\n")[0].strip()
                if "Observation:" in raw: d_obs = raw.split("Observation:", 1)[1].split("\n")[0].strip()
                if "Recommendation:" in raw: d_rec = raw.split("Recommendation:", 1)[1].split("\n")[0].strip()

            with st.form("entry_form"):
                name = st.text_input("Defect Title", value=d_def, help="Short summary (e.g. Cracked Tile)")
                
                c_obs, c_rew = st.columns([3, 1])
                obs = c_obs.text_area("Observation", value=d_obs, height=100, help="Technical description of the issue")
                if c_rew.form_submit_button("✨ Magic Rewrite"):
                    obs = ai.magic_rewrite(obs)
                    st.info("Rewritten: " + obs)
                
                rec = st.text_area("Recommendation", value=d_rec, help="What needs to be done?")
                sev = st.selectbox("Severity", SEVERITY_LEVELS, help="AS 4349.1 classification")
                
                cost = "N/A"
                if st.form_submit_button("💲 Get Cost Est."):
                    cost = ai.estimate_cost(name, sev)
                    st.warning(f"Est: {cost}")
                
                if st.form_submit_button("Save Defect"):
                    st.session_state['defects'].append({
                        "area": area, "defect_name": name, "observation": obs,
                        "severity": sev, "recommendation": rec, "cost": cost
                    })
                    st.success("Defect Logged")

    with col_sidebar:
        st.subheader("📝 Draft Items")
        if st.session_state['defects']:
            st.metric("Total Logged", len(st.session_state['defects']))
            df = pd.DataFrame(st.session_state['defects'])
            st.dataframe(df[['area', 'defect_name']], hide_index=True, use_container_width=True)
        else:
            st.info("No items yet.")

def report_page(ai: AIEngine):
    section_header("Report Studio", "file-text")
    
    if not st.session_state['defects']:
        st.warning("No data found. Please complete an inspection first.")
        return

    st.subheader("Edit Findings")
    df = pd.DataFrame(st.session_state['defects'])
    edited_df = st.data_editor(
        df, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "severity": st.column_config.SelectboxColumn("Severity", options=SEVERITY_LEVELS)
        }
    )
    st.session_state['defects'] = edited_df.to_dict('records')
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Executive Summary")
        if st.button("Generate Summary (AI)"):
            with st.spinner("Writing..."):
                st.session_state['summary'] = ai.generate_exec_summary(st.session_state['defects'])
        
        summ = st.text_area("Summary Text", st.session_state.get('summary', ''), height=150)

    with c2:
        st.subheader("Finalize & Export")
        accepted = st.checkbox("I certify this report meets AS 4349.1 standards.")
        
        if accepted:
            logo_file = st.session_state.get('logo_file')
            logo_bytes = io.BytesIO(logo_file.getvalue()) if logo_file else None
            
            pdf_data = generate_pdf_report(
                st.session_state['defects'],
                {"address": st.session_state.get('addr', ''), "client": st.session_state.get('client', '')},
                st.session_state['fullname'],
                {"name": st.session_state.get('co_name', 'SiteVision AI'), "lic": st.session_state.get('lic', ''), "logo": logo_bytes},
                summ
            )
            
            st.download_button(
                label="📄 Download Professional PDF",
                data=pdf_data,
                file_name=f"Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime='application/pdf',
                type='primary',
                use_container_width=True
            )

def dashboard_page():
    section_header("Dashboard", "bar-chart")
    
    defects = st.session_state.get('defects', [])
    score = 100
    for d in defects:
        if "Major" in d['severity']: score -= 15
        elif "Safety" in d['severity']: score -= 20
        else: score -= 5
    score = max(0, score)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Health Score", f"{score}/100")
    c2.metric("Active Defects", len(defects))
    c3.metric("System", "Online")
    
    st.markdown("### 📰 Industry News")
    news = fetch_news()
    if news:
        for n in news:
            st.markdown(f"**[{n['title']}]({n['link']})**")
            st.caption(n['summary'])
    else:
        st.caption("No news available currently.")

# --- MAIN CONTROLLER ---
def main():
    init_db()
    apply_custom_css()
    
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'defects' not in st.session_state: st.session_state['defects'] = []
    if 'page' not in st.session_state: st.session_state['page'] = 'New Inspection' # Set New Inspection as default landing
    
    ai = AIEngine(st.session_state.get('api_key'))
    
    if not st.session_state['logged_in']:
        login_page()
    else:
        with st.sidebar:
            st.markdown(get_logo_svg(), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Navigation
            menu_opts = ["New Inspection", "Dashboard", "Reports", "Site Safety", "Admin"]
            selected_page = st.radio("Navigate", menu_opts, index=menu_opts.index(st.session_state.get('page', 'New Inspection')))
            st.session_state['page'] = selected_page
            
            st.markdown("<hr>", unsafe_allow_html=True)
            with st.expander("⚙️ Settings"):
                st.session_state['api_key'] = st.text_input("AI Key", type="password", value=st.session_state.get('api_key', ''))
                st.session_state['co_name'] = st.text_input("Company", value="SiteVision AI")
                st.session_state['lic'] = st.text_input("Licence", value="AU-000")
                l = st.file_uploader("Logo", type=['png', 'jpg'])
                if l: st.session_state['logo_file'] = l

            if st.button("Logout", use_container_width=True):
                st.session_state.clear()
                st.rerun()

        pg = st.session_state['page']
        if pg == "New Inspection": inspection_page(ai)
        elif pg == "Dashboard": dashboard_page()
        elif pg == "Reports": report_page(ai)
        elif pg == "Admin": 
            if st.session_state['role'] == 'admin': admin_page()
            else: st.warning("Access Restricted")
        elif pg == "Site Safety": safety_page(ai)

if __name__ == '__main__':
    main()
