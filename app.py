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
import re
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

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
            --primary: #0F172A; /* Slate 900 */
            --accent: #3B82F6;  /* Electric Blue */
            --secondary: #64748B; /* Slate 500 */
            --bg: #F1F5F9;      /* Slate 100 */
            --card-bg: #FFFFFF;
        }

        .stApp {
            background-color: var(--bg);
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E2E8F0;
        }
        
        /* Professional Card Styling */
        div.stContainer, div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[data-testid="stVerticalBlock"] {
            background-color: var(--card-bg);
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
            border: 1px solid #E2E8F0;
            margin-bottom: 1rem;
        }
        
        /* Headers */
        h1, h2, h3 {
            color: var(--primary);
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        
        /* Accent Headers */
        h3 {
            border-left: 4px solid var(--accent);
            padding-left: 12px;
        }
        
        /* Primary Buttons */
        .stButton button {
            background-color: var(--accent);
            color: white;
            font-weight: 600;
            border-radius: 6px;
            border: none;
            height: 44px;
            transition: all 0.2s ease;
            width: 100%;
        }
        .stButton button:hover {
            background-color: #2563EB;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            transform: translateY(-1px);
        }

        /* Metrics Styling */
        [data-testid="stMetricValue"] {
            color: var(--accent);
            font-weight: 700;
        }
        
        /* Form Inputs */
        .stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
            border-radius: 6px;
            border: 1px solid #CBD5E1;
        }
        
        /* Custom Defect Card */
        .defect-card {
            background: #F8FAFC;
            border-left: 4px solid #F59E0B;
            padding: 10px;
            margin-bottom: 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }
        
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
        
        /* Financial Summary Box (for Final Report Page) */
        .financial-box {
            background-color: #EFF6FF;
            border: 1px solid #BFDBFE;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            margin-top: 20px;
        }
        .financial-total {
            font-size: 1.5em;
            font-weight: bold;
            color: #1E40AF;
        }
    </style>
    """, unsafe_allow_html=True)

def get_logo_svg():
    return """
    <svg width="100%" height="60" viewBox="0 0 250 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="10" y="10" width="40" height="40" rx="8" fill="#0F172A"/>
        <path d="M30 20L40 40H20L30 20Z" fill="#3B82F6"/>
        <circle cx="30" cy="32" r="3" fill="white"/>
        <text x="65" y="38" fill="#0F172A" font-family="Inter, sans-serif" font-weight="bold" font-size="24" letter-spacing="-0.5">SiteVision <tspan fill="#3B82F6">AI</tspan></text>
    </svg>
    """

# --- CONSTANTS & DATA ---
SEVERITY_LEVELS = [
    "Minor Defect (Maintenance)",
    "Major Defect (Structural/Significant)",
    "Safety Hazard (Immediate Action)",
    "Further Investigation Required"
]

AREAS = [
    "Site & Fencing", "Exterior Walls", "Sub-floor Space", "Roof Exterior", 
    "Roof Space", "Interior", "Garage/Carport", "Wet Areas", "Outbuildings"
]

# --- HELPER FUNCTIONS ---
def parse_cost(cost_str):
    """Extracts low and high values from strings like '$500 - $1,200'"""
    if not cost_str or cost_str == "N/A":
        return 0, 0
    # Find all numbers (removing commas and non-digits)
    nums = re.findall(r'\d+', cost_str.replace(',', ''))
    if not nums:
        return 0, 0
    nums = [int(n) for n in nums]
    if len(nums) == 1:
        return nums[0], nums[0]
    return min(nums), max(nums)

def calculate_total_repairs(defects):
    total_min = 0
    total_max = 0
    for d in defects:
        # Use the cost value from the dictionary (which might have been edited in the data editor)
        c_min, c_max = parse_cost(d.get('cost', 'N/A'))
        total_min += c_min
        total_max += c_max
    return total_min, total_max

# --- DATABASE (Mock SQLite for Auth) ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, full_name TEXT)''')
    # Default password 'inspect' hashed
    secure_pass = hashlib.sha256(b"inspect").hexdigest()
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin', ?, 'admin', 'System Administrator')", (secure_pass,))
    else:
        # Ensure default pass is always set for easy testing
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
        self.model = None
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analyze_photo(self, image):
        if not self.model: return None
        prompt = """
        Act as an Australian Building Inspector. Analyze this image.
        Reference AS 4349.1.
        Format:
        Defect: [Name]
        Observation: [Technical Description]
        Severity: [Minor/Major/Safety]
        Recommendation: [Action]
        """
        try: return self.model.generate_content([prompt, image]).text
        except: return "AI Error"

    def generate_scope(self, defect, rec):
        if not self.model: return "N/A"
        prompt = f"Write a detailed Scope of Works for a tradesperson to rectify '{defect}'. Recommendation was: '{rec}'. Use Australian trade terminology."
        try: return self.model.generate_content(prompt).text
        except: return "N/A"

    def explain_impact(self, defect):
        if not self.model: return "N/A"
        prompt = f"Explain the consequences to the property owner if '{defect}' is not fixed. Focus on structural integrity and cost escalation."
        try: return self.model.generate_content(prompt).text
        except: return "N/A"

    def check_compliance(self, query):
        if not self.model: return "N/A"
        prompt = f"Search NCC 2022 Vol 2 and AS standards for: '{query}'. Cite the specific clause if possible."
        try: return self.model.generate_content(prompt).text
        except: return "N/A"

    def suggest_trade(self, defect):
        if not self.model: return "Builder"
        prompt = f"Which specific Australian licensed trade is best suited to fix '{defect}'? (e.g. Roof Plumber, Electrician, Structural Engineer)."
        try: return self.model.generate_content(prompt).text.strip()
        except: return "General Builder"

    def generate_maintenance(self, age, defects):
        if not self.model: return "N/A"
        d_list = ", ".join([d['defect_name'] for d in defects])
        prompt = f"Create a 5-year maintenance schedule for a house built in {age} with these current defects: {d_list}. Format as a list."
        try: return self.model.generate_content(prompt).text
        except: return "N/A"

    def magic_rewrite(self, text):
        if not self.model: return text
        return self.model.generate_content(f"Rewrite as formal building report text (AS 4349.1): {text}").text.strip()

    def estimate_cost(self, defect, severity):
        if not self.model: return "N/A"
        # Uses specific prompt to force a parsable output range
        prompt = f"Provide a repair cost range in AUD for '{defect}' ({severity}) in Australia. Return ONLY the range string (e.g. '$500 - $1,000'). Do not add any other text."
        try: return self.model.generate_content(prompt).text.strip()
        except: return "N/A"

    def generate_exec_summary(self, defects, total_cost):
        if not self.model: return ""
        d_list = ", ".join([f"{d['defect_name']} ({d['severity']})" for d in defects])
        prompt = f"Write an Executive Summary for a building report. Defects: {d_list}. Total Estimated Rectification Cost: {total_cost}. Focus on major risks and required immediate action."
        try: return self.model.generate_content(prompt).text
        except: return ""

# --- EXPORT ENGINES (PDF/DOCX) ---
class ReportPDF(FPDF):
    def __init__(self, company, license, logo_path, header_img, footer_img):
        super().__init__()
        self.company = company
        self.license = license
        self.logo_path = logo_path
        self.header_img = header_img
        self.footer_img = footer_img

    def header(self):
        if self.header_img:
            try: self.image(self.header_img, 0, 0, 210)
            except: pass
        
        if self.logo_path and not self.header_img:
            try: self.image(self.logo_path, 10, 8, 35)
            except: pass
            
        self.ln(25)
        if not self.header_img:
            self.set_font('Arial', 'B', 16)
            self.cell(0, 10, f"{self.company} - Inspection Report", 0, 1, 'R')
            self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        if self.footer_img:
            try: self.image(self.footer_img, 0, 270, 210)
            except: pass
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, 'C')

def generate_pdf(data, prop, inspector, co_details, summary, total_est_str):
    logo = io.BytesIO(co_details['logo'].getvalue()) if co_details['logo'] else None
    hed = io.BytesIO(co_details['header'].getvalue()) if co_details['header'] else None
    foot = io.BytesIO(co_details['footer'].getvalue()) if co_details['footer'] else None

    pdf = ReportPDF(co_details['name'], co_details['lic'], logo, hed, foot)
    pdf.add_page()
    
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Property Overview", 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.cell(40, 7, "Address:", 0); pdf.cell(0, 7, prop['address'], 0, 1)
    pdf.cell(40, 7, "Client:", 0); pdf.cell(0, 7, prop['client'], 0, 1)
    pdf.ln(5)
    
    # Executive Summary
    pdf.set_fill_color(240, 245, 255)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "  Executive Summary", 0, 1, 'L', 1)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, summary)
    pdf.ln(5)

    # Financial Summary (The Calculator Result)
    pdf.set_fill_color(255, 247, 237) # Light Orange
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "  Financial Estimate", 0, 1, 'L', 1)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 10, f"Total Estimated Rectification Costs: {total_est_str}", 0, 1)
    pdf.set_font('Arial', 'I', 9)
    pdf.multi_cell(0, 5, "Note: These costs are rough estimates generated by AI based on average Australian trade rates and edited by the inspector. Actual quotes from licensed trades should be sought.")
    pdf.ln(8)
    
    # Detailed Defects
    for item in data:
        pdf.set_font('Arial', 'B', 11)
        if "Safety" in item['severity']: pdf.set_text_color(200, 0, 0)
        elif "Major" in item['severity']: pdf.set_text_color(200, 100, 0)
        else: pdf.set_text_color(0, 50, 150)
        
        pdf.cell(0, 8, f"{item['area']} | {item['defect_name']}", 0, 1)
        pdf.set_text_color(0)
        
        pdf.set_font('Arial', '', 10)
        pdf.multi_cell(0, 5, f"Observation: {item['observation']}")
        pdf.multi_cell(0, 5, f"Rectification: {item['recommendation']}")
        
        # Cost Line
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(30, 6, "Est. Repair Cost:", 0)
        pdf.set_font('Arial', '', 9)
        pdf.cell(0, 6, f"{item.get('cost', 'N/A')}", 0, 1)
        
        if 'scope' in item and item['scope']:
            pdf.set_font('Arial', 'I', 9)
            pdf.multi_cell(0, 5, f"Scope: {item['scope']}")
            
        pdf.ln(4)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
        
    return pdf.output(dest='S').encode('latin-1')

def generate_docx(data, prop, inspector, co_details, summary, total_est_str):
    doc = Document()
    
    # Header
    section = doc.sections[0]
    header = section.header
    htable = header.add_table(1, 2, width=Inches(6))
    htable.autofit = False
    htable.columns[0].width = Inches(2)
    htable.columns[1].width = Inches(4)
    
    if co_details['logo']:
        logo_stream = io.BytesIO(co_details['logo'].getvalue())
        htable.cell(0,0).paragraphs[0].add_run().add_picture(logo_stream, width=Inches(1.5))
    
    htable.cell(0,1).text = f"{co_details['name']}\nLicence: {co_details['lic']}\nAS 4349.1 Inspection Report"
    
    # Body
    doc.add_heading('Property Inspection Report', 0)
    
    p = doc.add_paragraph()
    p.add_run(f"Address: {prop['address']}\n").bold = True
    p.add_run(f"Client: {prop['client']}\n")
    p.add_run(f"Inspector: {inspector}\n")
    p.add_run(f"Date: {datetime.now().strftime('%d/%m/%Y')}")
    
    doc.add_heading('Executive Summary', level=1)
    doc.add_paragraph(summary)

    # Financial Section (The Calculator Result)
    doc.add_heading('Estimated Repair Costs', level=1)
    p_fin = doc.add_paragraph()
    p_fin.add_run(f"Total Estimate: {total_est_str}").bold = True
    p_fin.add_run("\n*These estimates are indicative only and subject to trade quotes.").italic = True
    
    doc.add_heading('Defect Register', level=1)
    
    for item in data:
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        
        img_cell = table.cell(0, 0)
        paragraph = img_cell.paragraphs[0]
        if 'image_data' in item and item['image_data']:
            try:
                img_bytes = base64.b64decode(item['image_data'])
                img_stream = io.BytesIO(img_bytes)
                # Max width for DOCX cell
                paragraph.add_run().add_picture(img_stream, width=Inches(2.5)) 
            except:
                paragraph.text = "[Image Error]"
        else:
            paragraph.text = "[No Image]"
            
        txt_cell = table.cell(0, 1)
        txt_cell.text = ""
        p = txt_cell.add_paragraph()
        p.add_run(f"{item['defect_name']}").bold = True
        p.add_run(f"\nArea: {item['area']}")
        # Highlight severity color (basic attempt, DOCX styles are complex)
        severity_run = p.add_run(f"\nSeverity: {item['severity']}")
        if "Major" in item['severity'] or "Safety" in item['severity']:
             severity_run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00) # Red
        
        p.add_run("\n\nObservation:").bold = True
        p.add_run(f" {item['observation']}")
        
        p.add_run("\n\nRecommendation:").bold = True
        p.add_run(f" {item['recommendation']}")
        
        p.add_run("\n\nEst. Cost: ").bold = True
        p.add_run(f"{item.get('cost', 'N/A')}")

        # Add scope if present
        if item.get('scope'):
            p.add_run("\nScope of Works: ").bold = True
            p.add_run(f"{item['scope']}")

        doc.add_paragraph("")

    f = io.BytesIO()
    doc.save(f)
    return f.getvalue()

# --- UI MODULES ---
def login_page():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(get_logo_svg(), unsafe_allow_html=True)
        st.markdown("""
        <div style='background:white; padding:40px; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.05); margin-top:20px; text-align:center;'>
            <h3 style='color:#0F172A;'>Inspector Portal</h3>
            <p style='color:#64748B; font-size:0.9em;'>Enterprise Edition v6.0</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            u = st.text_input("Username", help="Enter your registered ID")
            p = st.text_input("Password", type="password")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Secure Login"):
                user = check_login(u, p)
                if user:
                    # User logged in successfully
                    st.session_state.update({'logged_in': True, 'role': user[0], 'fullname': user[1], 'page': 'New Inspection'})
                    st.rerun()
                else: st.error("Access Denied")

def inspection_page(ai: AIEngine):
    section_header("New Inspection", "clipboard")
    
    # Save/Restore
    with st.expander("💾 Session Controls"):
        c1, c2 = st.columns(2)
        # Download defect list as JSON
        c1.download_button("Backup Session (JSON)", json.dumps(st.session_state['defects']), "draft.json", "application/json")
        up = c2.file_uploader("Restore Session", type=['json'])
        if up:
            st.session_state['defects'] = json.load(up)
            st.rerun()

    with st.container():
        st.subheader("📍 Property Scope")
        c1, c2, c3 = st.columns([2, 1, 1])
        st.session_state['addr'] = c1.text_input("Address", st.session_state.get('addr', ''))
        st.session_state['client'] = c2.text_input("Client", st.session_state.get('client', ''))
        year = c3.number_input("Year Built", 1900, 2025, st.session_state.get('year_built', 2000))
        st.session_state['year_built'] = year
        
        # Maintenance Plan Generation
        if year and st.button("Generate Maintenance Plan (AI)"):
            with st.spinner("Building 5-Year Plan..."):
                plan = ai.generate_maintenance(year, st.session_state['defects'])
                st.session_state['maint_plan'] = plan
                st.info("Maintenance Plan Generated (See Reports)")

    st.markdown("<br>", unsafe_allow_html=True)

    col_main, col_sidebar = st.columns([1.6, 1])
    
    with col_main:
        section_header("Defect Entry", "camera")
        with st.container():
            area = st.selectbox("Area Inspected", AREAS)
            
            st.markdown("##### 📸 Evidence")
            img_file = st.file_uploader("Upload Photo", type=['jpg', 'png'])
            
            ai_data = None
            b64_str = None
            if img_file:
                b = img_file.getvalue()
                b64_str = base64.b64encode(b).decode()
                # Display image with hover zoom effect
                st.markdown(f'<img src="data:image/png;base64,{b64_str}" class="hover-zoom" width="150">', unsafe_allow_html=True)
                
                # AI Analysis button
                if st.button("Analyze Compliance (AI)"):
                    with st.spinner("Checking AS 4349.1..."):
                        ai_data = ai.analyze_photo(Image.open(img_file))
                        st.session_state['temp_ai'] = ai_data

            # Pre-fill fields if AI data exists from analysis
            d_d, d_o, d_r = "", "", ""
            if 'temp_ai' in st.session_state and st.session_state['temp_ai']:
                raw = st.session_state['temp_ai']
                if "Defect:" in raw: d_d = raw.split("Defect:", 1)[1].split("\n")[0].strip()
                if "Observation:" in raw: d_o = raw.split("Observation:", 1)[1].split("\n")[0].strip()
                if "Recommendation:" in raw: d_r = raw.split("Recommendation:", 1)[1].split("\n")[0].strip()
                # Clear temporary AI data after pre-fill
                # st.session_state['temp_ai'] = None 

            with st.form("defect"):
                name = st.text_input("Defect Title", value=d_d)
                obs = st.text_area("Observation", value=d_o, height=100)
                rec = st.text_area("Recommendation", value=d_r, height=100)
                sev = st.selectbox("Severity", SEVERITY_LEVELS)
                
                c_a, c_b, c_c = st.columns(3)
                want_scope = c_a.checkbox("Generate Scope of Works")
                want_impact = c_b.checkbox("Add Impact Analysis")
                want_trade = c_c.checkbox("Suggest Trade")
                
                # Form submission handles saving and AI generation
                if st.form_submit_button("Save Defect"):
                    # Run AI tasks
                    scope_txt, impact_txt, trade_txt = "", "", ""
                    
                    # Estimate cost automatically (MANDATORY feature)
                    cost_est_val = "N/A"
                    if name and sev:
                        try:
                            cost_est_val = ai.estimate_cost(name, sev)
                        except Exception as e: 
                            print(f"Cost estimation failed: {e}")
                            pass

                    if want_scope: scope_txt = ai.generate_scope(name, rec)
                    if want_impact: impact_txt = ai.explain_impact(name)
                    if want_trade: trade_txt = ai.suggest_trade(name)
                    
                    # Save the new defect
                    st.session_state['defects'].append({
                        "area": area, "defect_name": name, "observation": obs,
                        "severity": sev, "recommendation": rec,
                        "scope": scope_txt, "impact": impact_txt, "trade": trade_txt,
                        "cost": cost_est_val, # AI generated or N/A
                        "image_data": b64_str
                    })
                    st.success(f"Defect '{name}' saved to Draft (Cost: {cost_est_val})")
                    # Clear temp AI data after successful save
                    st.session_state['temp_ai'] = None
                    st.rerun() # Rerun to clear form

    with col_sidebar:
        st.subheader("📋 Draft Register")
        if st.session_state['defects']:
            # Calculate running total for display in the draft sidebar
            t_min, t_max = calculate_total_repairs(st.session_state['defects'])
            total_str = f"${t_min:,} - ${t_max:,}"
            st.markdown(f"**Total Draft Est:** <span style='color:#3B82F6;'>{total_str}</span>", unsafe_allow_html=True)
            st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)
            
            for i, d in enumerate(st.session_state['defects']):
                st.markdown(f"""
                <div class="defect-card">
                    <b>{d['area']}</b><br>
                    {d['defect_name']}<br>
                    <span style="color:#EF4444; font-size:0.8em;">{d['severity'].split('(')[0]}</span><br>
                    <span style="color:#059669; font-size:0.8em;">Est: {d.get('cost','N/A')}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No defects logged.")

def report_page(ai: AIEngine):
    section_header("Finalize Report: Review & Edit", "file-text")
    
    # Branding Options
    with st.expander("🎨 Report Branding", expanded=False):
        c1, c2, c3 = st.columns(3)
        st.session_state['header_img'] = c1.file_uploader("Header Image (PDF/DOCX)", type=['png', 'jpg'])
        st.session_state['footer_img'] = c2.file_uploader("Footer Image (PDF)", type=['png', 'jpg'])
        # Add a placeholder for maintenance plan visibility
        if st.session_state.get('maint_plan'):
            c3.info("Maintenance Plan Ready")
            with c3.expander("View Plan"):
                st.markdown(st.session_state['maint_plan'])

    st.subheader("Final Defect Register Review")
    
    if st.session_state['defects']:
        # Convert defects list to DataFrame for the data editor
        df = pd.DataFrame(st.session_state['defects'])
        
        # Use data editor to allow inspector to make final manual edits (especially to cost)
        edited_df = st.data_editor(
            df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "severity": st.column_config.SelectboxColumn("Severity", options=SEVERITY_LEVELS),
                "cost": st.column_config.TextColumn("Est Cost ($)", help="Enter range e.g. $500 - $1,000")
            },
            # Hide complex data fields not needed for quick review, but keep 'image_data'
            # The columns list must match the columns in the DataFrame
            hide_index=True,
            column_order=["area", "defect_name", "severity", "observation", "recommendation", "trade", "cost", "scope", "impact", "image_data"]
        )
        # Update session state with the edited data
        st.session_state['defects'] = edited_df.to_dict('records')
        
        # CALCULATE TOTALS from the edited data
        t_min, t_max = calculate_total_repairs(st.session_state['defects'])
        total_str = f"${t_min:,} - ${t_max:,}"
        
        # Display Financial Box prominently
        st.markdown(f"""
        <div class="financial-box">
            <h3>💰 Total Estimated Repair Costs</h3>
            <div class="financial-total">{total_str}</div>
            <p><i>This figure includes all line items above and is editable via the table.</i></p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr>", unsafe_allow_html=True)

        # Executive Summary Generation
        if st.button("Generate Exec Summary (AI)"):
            st.session_state['summary'] = ai.generate_exec_summary(st.session_state['defects'], total_str)
            
        summ = st.text_area("Executive Summary (Final Edit)", st.session_state.get('summary', ''), height=200)
        
        c1, c2 = st.columns(2)
        
        # PDF Export
        if c1.button("Download PDF Report"):
            pdf_dat = generate_pdf(
                st.session_state['defects'],
                {"address": st.session_state.get('addr', ''), "client": st.session_state.get('client', '')},
                st.session_state['fullname'],
                {"name": st.session_state.get('co_name', ''), "lic": st.session_state.get('lic', ''), 
                 "logo": st.session_state.get('logo_file'), "header": st.session_state.get('header_img'), 
                 "footer": st.session_state.get('footer_img')},
                summ,
                total_str # Pass the calculated total string
            )
            st.download_button("Get PDF", pdf_dat, f"Inspection_Report_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")
            
        # DOCX Export
        if c2.button("Download Word (DOCX)"):
            docx_dat = generate_docx(
                st.session_state['defects'],
                {"address": st.session_state.get('addr', ''), "client": st.session_state.get('client', '')},
                st.session_state['fullname'],
                {"name": st.session_state.get('co_name', ''), "lic": st.session_state.get('lic', ''), 
                 "logo": st.session_state.get('logo_file')},
                summ,
                total_str # Pass the calculated total string
            )
            st.download_button("Get DOCX", docx_dat, f"Inspection_Report_{datetime.now().strftime('%Y%m%d')}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    else:
        st.info("No defects have been logged yet. Please start a new inspection first.")

def section_header(text, icon):
    # This is a cosmetic header function
    st.markdown(f"""
    <div style="display: flex; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #E2E8F0; padding-bottom: 10px;">
        <h2 style="margin: 0; color: #0F172A;">{text}</h2>
    </div>
    """, unsafe_allow_html=True)

# --- MAIN APPLICATION ENTRY POINT ---
def main():
    init_db()
    apply_custom_css()
    
    # Initialize session state variables
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'defects' not in st.session_state: st.session_state['defects'] = []
    if 'page' not in st.session_state: st.session_state['page'] = 'New Inspection'
    
    # Initialize AI Engine (needs API key from settings)
    ai = AIEngine(st.session_state.get('api_key'))
    
    if not st.session_state['logged_in']:
        login_page()
    else:
        # Sidebar Navigation
        with st.sidebar:
            st.markdown(get_logo_svg(), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            menu = ["New Inspection", "Dashboard", "Finalize Report", "Admin"]
            pg = st.radio("Navigate", menu, index=menu.index(st.session_state['page']) if st.session_state['page'] in menu else 0)
            st.session_state['page'] = pg
            
            with st.expander("⚙️ Settings"):
                st.session_state['api_key'] = st.text_input("AI Key", type="password", value=st.session_state.get('api_key', ''))
                st.session_state['co_name'] = st.text_input("Company Name", value=st.session_state.get('co_name', 'SiteVision Pty Ltd'))
                st.session_state['lic'] = st.text_input("Inspector Licence", value=st.session_state.get('lic', 'AU-4349'))
                st.session_state['logo_file'] = st.file_uploader("Company Logo", type=['png', 'jpg'])
                
            if st.button("Logout"):
                st.session_state.clear()
                st.rerun()

        # Page Routing
        if pg == "New Inspection": 
            inspection_page(ai)
        elif pg == "Dashboard": 
            section_header("Dashboard", "")
            # Recalculate totals for dashboard metric
            t_min, t_max = calculate_total_repairs(st.session_state['defects'])
            total_str = f"${t_min:,} - ${t_max:,}"

            c1,c2,c3 = st.columns(3)
            c1.metric("Defects Logged", len(st.session_state['defects']))
            c2.metric("Total Est. Cost", total_str)
            c3.metric("Status", "Inspection in Progress")
            
            if st.session_state.get('maint_plan'):
                st.markdown("---")
                st.subheader("5-Year Maintenance Plan")
                st.markdown(st.session_state['maint_plan'])

        elif pg == "Finalize Report": 
            report_page(ai)
        elif pg == "Admin": 
            if st.session_state['role'] == 'admin': 
                st.write("Admin Panel: Manage Users (Not Implemented in Mock)") 
            else: st.error("Access Restricted to Administrators")

if __name__ == '__main__':
    main()
