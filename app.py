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

# --- CONFIGURATION & SETUP ---
st.set_page_config(
    page_title="InspectPro | Professional Building Inspection",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS & THEME ---
def apply_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #1e293b;
        }
        
        /* Main Background */
        .stApp {
            background-color: #f1f5f9;
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
        }
        
        /* Headers */
        h1, h2, h3 {
            color: #0f172a;
            font-weight: 700;
            letter-spacing: -0.025em;
        }
        
        /* Cards/Containers */
        .stContainer, [data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] {
            background-color: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
            border: 1px solid #e2e8f0;
        }
        
        /* Primary Buttons */
        .stButton button {
            background-color: #2563eb;
            color: white;
            border-radius: 8px;
            font-weight: 600;
            border: none;
            padding: 0.5rem 1rem;
            transition: all 0.2s;
        }
        .stButton button:hover {
            background-color: #1d4ed8;
            box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
        }
        
        /* Inputs */
        .stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
            border-radius: 8px;
            border-color: #cbd5e1;
        }
        
        /* Metrics */
        [data-testid="stMetricValue"] {
            color: #2563eb;
            font-weight: 700;
        }
        
        /* Login Box Container Specifics */
        .login-container {
            max-width: 400px;
            margin: 0 auto;
        }
    </style>
    """, unsafe_allow_html=True)

def get_logo_svg():
    """Returns the SVG code for the embedded logo"""
    return """
    <svg width="100%" height="50" viewBox="0 0 220 50" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="5" width="40" height="40" rx="8" fill="#2563EB"/>
        <path d="M20 15L30 35H10L20 15Z" fill="white"/>
        <rect x="16" y="30" width="8" height="8" fill="white"/>
        <text x="50" y="33" fill="#0F172A" font-family="Inter, sans-serif" font-weight="bold" font-size="24">Inspect<tspan fill="#2563EB">Pro</tspan></text>
    </svg>
    """

# --- CONSTANTS & STANDARDS (AS 4349.1) ---
SEVERITY_LEVELS = [
    "Minor Defect (Maintenance)",
    "Major Defect (Structural/Significant)",
    "Safety Hazard (Urgent)",
    "Further Investigation Required"
]

AREAS = [
    "Site & Fencing",
    "Exterior",
    "Sub-floor Space",
    "Roof Exterior",
    "Roof Space",
    "Interior",
    "Garage/Carport",
    "Wet Areas"
]

COMMON_DEFECTS = {
    "Interior": [
        {"name": "Drummy Tiles", "obs": "Hollow sound detected when tapping floor tiles, indicating loss of adhesion.", "rec": "Engage a tiler to remove and re-fix affected tiles.", "sev": "Minor Defect (Maintenance)"},
        {"name": "Settlement Cracks", "obs": "Minor hairline cracking observed to cornices/plasterboard.", "rec": "Patch and paint as part of normal maintenance.", "sev": "Minor Defect (Maintenance)"},
        {"name": "Moisture Ingress", "obs": "High moisture readings and staining visible on wall.", "rec": "Investigate source of leak immediately and repair.", "sev": "Major Defect (Structural/Significant)"}
    ],
    "Exterior": [
        {"name": "Cracked Brickwork", "obs": "Stepped cracking visible in masonry walls.", "rec": "Engage a structural engineer to assess foundation movement.", "sev": "Major Defect (Structural/Significant)"},
        {"name": "Timber Rot", "obs": "Fungal decay (rot) visible in window frames.", "rec": "Joiner to cut out rot and splice in new timber or replace unit.", "sev": "Major Defect (Structural/Significant)"}
    ],
    "Roof Exterior": [
        {"name": "Broken Tiles", "obs": "Cracked and displaced roof tiles visible.", "rec": "Replace damaged tiles to prevent water ingress.", "sev": "Minor Defect (Maintenance)"},
        {"name": "Blocked Gutters", "obs": "Significant debris buildup in gutters.", "rec": "Clean gutters to prevent overflow and backflow.", "sev": "Minor Defect (Maintenance)"}
    ],
    "Sub-floor Space": [
        {"name": "Damp Soil", "obs": "Soil in subfloor is excessively damp.", "rec": "Improve subfloor ventilation and drainage.", "sev": "Major Defect (Structural/Significant)"},
        {"name": "Termite Barrier Breached", "obs": "Termite shielding physically damaged or bridged.", "rec": "Pest controller to inspect and repair barrier immediately.", "sev": "Safety Hazard (Urgent)"}
    ]
}

# --- DATABASE HANDLING ---
def init_db():
    """Initialize SQLite DB and handle admin password resets."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, full_name TEXT)''')
    
    # Hash for 'inspect' - SHA256
    secure_pass = hashlib.sha256(b"inspect").hexdigest()
    
    # Check for admin
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin', ?, 'admin', 'Principal Inspector')", (secure_pass,))
    else:
        # Force update password to ensure 'inspect' works (fixes login issues)
        c.execute("UPDATE users SET password = ? WHERE username = 'admin'", (secure_pass,))
        
    conn.commit()
    conn.close()

def check_login(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT role, full_name FROM users WHERE username = ? AND password = ?", (username, hashed_pw))
    user = c.fetchone()
    conn.close()
    return user

def add_user(username, password, role, full_name):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (username, hashed_pw, role, full_name))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def get_all_users():
    conn = sqlite3.connect('users.db')
    df = pd.read_sql_query("SELECT username, role, full_name FROM users", conn)
    conn.close()
    return df

# --- AI INTEGRATION ---
def analyze_image_with_ai(image, api_key):
    if not api_key:
        return "Error: Please provide a Google Gemini API Key in settings."
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
        Act as a qualified Australian Building Inspector compliant with AS 4349.1.
        Analyze this image of a building defect.
        Provide a response in this exact format:
        
        Defect: [Short, professional name]
        Observation: [Technical description of the visual evidence]
        Severity: [Choose strictly one: Minor Defect (Maintenance), Major Defect (Structural/Significant), Safety Hazard (Urgent)]
        Recommendation: [Standard remedial advice suitable for a report]
        """
        
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        return f"AI Analysis Failed: {str(e)}"

# --- PDF GENERATION CLASS ---
class InspectionPDF(FPDF):
    def __init__(self, company_name, license_no, logo_path=None):
        super().__init__()
        self.company_name = company_name
        self.license_no = license_no
        self.logo_path = logo_path

    def header(self):
        if self.logo_path:
            try:
                # Logo handling
                self.image(self.logo_path, 10, 10, 30)
            except: pass
        
        self.set_font('Arial', 'B', 16)
        # Offset title if logo exists
        if self.logo_path: self.cell(35)
        self.cell(0, 10, f'{self.company_name} - Inspection Report', 0, 1, 'L')
        
        if self.logo_path: self.cell(35)
        self.set_font('Arial', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f'Licence No: {self.license_no} | Compliant with AS 4349.1', 0, 1, 'L')
        self.set_text_color(0)
        self.ln(15)
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Generated by InspectPro - {self.company_name} | Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(240, 244, 248) # Light gray/blue
        self.cell(0, 8, f"  {label}", 0, 1, 'L', 1)
        self.ln(4)

def generate_final_pdf(report_data, prop_details, inspector, company, license_num, logo_file):
    logo_path = None
    if logo_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(logo_file.getvalue())
            logo_path = tmp.name

    pdf = InspectionPDF(company, license_num, logo_path)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 1. Property Details Section
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Property Inspection Details", 0, 1)
    pdf.set_font('Arial', '', 10)
    
    # Grid layout for details
    pdf.cell(30, 7, "Address:", 0); pdf.cell(0, 7, prop_details['address'], 0, 1)
    pdf.cell(30, 7, "Client:", 0); pdf.cell(0, 7, prop_details['client'], 0, 1)
    pdf.cell(30, 7, "Date:", 0); pdf.cell(0, 7, datetime.now().strftime('%d %B %Y'), 0, 1)
    pdf.cell(30, 7, "Inspector:", 0); pdf.cell(0, 7, inspector, 0, 1)
    pdf.ln(10)

    # 2. Executive Summary
    pdf.chapter_title("Executive Summary")
    minor_count = len([x for x in report_data if "Minor" in x['severity']])
    major_count = len([x for x in report_data if "Major" in x['severity']])
    safety_count = len([x for x in report_data if "Safety" in x['severity']])
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(255, 255, 255)
    
    # Draw summary boxes
    start_y = pdf.get_y()
    pdf.rect(10, start_y, 60, 15); pdf.text(15, start_y + 10, f"Major Defects: {major_count}")
    pdf.rect(75, start_y, 60, 15); pdf.text(80, start_y + 10, f"Safety Hazards: {safety_count}")
    pdf.rect(140, start_y, 60, 15); pdf.text(145, start_y + 10, f"Minor Defects: {minor_count}")
    pdf.ln(20)

    # 3. Defects
    pdf.chapter_title("Defect Findings")
    if not report_data:
        pdf.cell(0, 10, "No significant defects recorded during this inspection.", 0, 1)
    
    for item in report_data:
        # Defect Header
        pdf.set_font('Arial', 'B', 11)
        if "Safety" in item['severity']: pdf.set_text_color(220, 38, 38) # Red
        elif "Major" in item['severity']: pdf.set_text_color(234, 88, 12) # Orange
        else: pdf.set_text_color(37, 99, 235) # Blue
            
        pdf.cell(0, 8, f"{item['area']} - {item['defect_name']}", 0, 1)
        pdf.set_text_color(0)
        
        # Details
        pdf.set_font('Arial', 'B', 9); pdf.cell(30, 5, "Severity:", 0)
        pdf.set_font('Arial', '', 9); pdf.cell(0, 5, item['severity'], 0, 1)
        
        pdf.set_font('Arial', 'B', 9); pdf.cell(30, 5, "Observation:", 0)
        pdf.set_font('Arial', '', 9); pdf.multi_cell(0, 5, item['observation'])
        
        pdf.set_font('Arial', 'B', 9); pdf.cell(30, 5, "Recommendation:", 0)
        pdf.set_font('Arial', '', 9); pdf.multi_cell(0, 5, item['recommendation'])
        
        pdf.ln(3)
        pdf.set_draw_color(230, 230, 230)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.set_draw_color(0)
        pdf.ln(5)

    # 4. Disclaimer
    pdf.add_page()
    pdf.chapter_title("Conditions & Limitations")
    disclaimer = """
    This report complies with Australian Standard AS 4349.1-2007 Inspection of Buildings.
    
    1. SCOPE: The inspection comprised a visual assessment of the property to identify major defects, safety hazards, and minor defects.
    2. LIMITATIONS: This inspection was non-invasive. No dismantling of building elements, moving of furniture, or cutting into walls/floors was undertaken. Defects concealed behind walls, floors, or ceilings are excluded.
    3. ELECTRICAL/PLUMBING: Services were checked for visible signs of damage only. No compliance certification is implied.
    4. PESTS: Unless specifically stated, this report does not cover timber pest activity (termites/borers) which requires a separate inspection under AS 4349.3.
    """
    pdf.set_font('Arial', '', 9)
    pdf.multi_cell(0, 6, disclaimer)

    # Cleanup
    if logo_path and os.path.exists(logo_path): os.unlink(logo_path)
    return pdf.output(dest='S').encode('latin-1')

# --- UI: LOGIN PAGE ---
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        # Embedded Logo
        st.markdown(get_logo_svg(), unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background-color: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border: 1px solid #e2e8f0; margin-top: 20px;">
            <h3 style="text-align: center; margin-bottom: 1.5rem; color: #1e293b;">Inspector Portal</h3>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("Secure Login", use_container_width=True)
            
            if submit:
                user = check_login(username, password)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.session_state['role'] = user[0]
                    st.session_state['fullname'] = user[1]
                    st.rerun()
                else:
                    st.error("Access Denied. Check your credentials.")

# --- UI: SIDEBAR ---
def sidebar_nav():
    with st.sidebar:
        st.markdown(get_logo_svg(), unsafe_allow_html=True)
        st.markdown("---")
        
        # Modern navigation using radio for better state management
        menu_options = ["Dashboard", "New Inspection", "Report Generator", "Industry News"]
        if st.session_state['role'] == 'admin':
            menu_options.append("Admin Settings")
            
        choice = st.radio("Navigation", menu_options, label_visibility="collapsed")
        
        st.markdown("---")
        st.markdown("### ⚙️ Settings")
        
        with st.expander("Company Branding"):
            st.session_state['co_name'] = st.text_input("Company Name", value=st.session_state.get('co_name', 'My Inspection Co'))
            st.session_state['lic_no'] = st.text_input("Licence No.", value=st.session_state.get('lic_no', 'AU-12345'))
            uploaded_logo = st.file_uploader("Upload Logo (PNG)", type=['png', 'jpg'])
            if uploaded_logo: st.session_state['logo_file'] = uploaded_logo

        with st.expander("AI Configuration"):
            api_key = st.text_input("Gemini API Key", type="password", value=st.session_state.get('api_key', ''))
            if api_key: st.session_state['api_key'] = api_key
            st.caption("[Get Free Key](https://aistudio.google.com/)")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sign Out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
            
        return choice

# --- PAGE: DASHBOARD ---
def dashboard():
    st.title(f"Welcome back, {st.session_state['fullname'].split()[0]}")
    st.markdown("Here is your inspection overview for today.")
    
    # Metrics
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Inspections Active", "1", delta="On Track")
    with c2:
        st.metric("Reports Pending", "1", delta="-1")
    with c3:
        st.metric("AI Credits", "Unlimited", delta="Free Tier")
    
    st.markdown("### Quick Actions")
    col1, col2 = st.columns(2)
    with col1:
        with st.container():
            st.subheader("🚀 Start Inspection")
            st.write("Begin a new site inspection compliance workflow.")
            st.info("Go to 'New Inspection' tab")
    with col2:
        with st.container():
            st.subheader("📄 View Drafts")
            st.write("Resume editing the current report in progress.")
            st.success(f"Current Draft: {len(st.session_state['inspection_data'])} items")

# --- PAGE: INSPECTION FORM ---
def inspection_form():
    st.title("📍 Site Inspection")
    
    # Property Context
    with st.container():
        c1, c2, c3 = st.columns([2, 1, 1])
        st.session_state['prop_addr'] = c1.text_input("Property Address", st.session_state.get('prop_addr', ''))
        st.session_state['client_nm'] = c2.text_input("Client Name", st.session_state.get('client_nm', ''))
        st.session_state['weather'] = c3.text_input("Weather", st.session_state.get('weather', 'Fine'))

    st.markdown("---")
    st.subheader("📝 Defect Logger")
    
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        area = st.selectbox("1. Select Area", AREAS)
        
        # Defect Library Toggle
        use_lib = st.checkbox("Use Defect Library")
        lib_prefill = None
        if use_lib and area in COMMON_DEFECTS:
            def_names = [d['name'] for d in COMMON_DEFECTS[area]]
            sel_def = st.selectbox("Quick Select", def_names)
            lib_prefill = next(d for d in COMMON_DEFECTS[area] if d['name'] == sel_def)

        # AI Toggle
        st.markdown("---")
        st.markdown("**🤖 AI Analysis**")
        uploaded_photo = st.file_uploader("Upload Photo", type=['jpg', 'png'])
        ai_res = None
        if uploaded_photo and st.session_state.get('api_key'):
            if st.button("Analyze Image"):
                with st.spinner("AI Inspector analyzing..."):
                    img = Image.open(uploaded_photo)
                    ai_res = analyze_image_with_ai(img, st.session_state['api_key'])
                    st.session_state['last_ai_res'] = ai_res
                    st.success("Analysis Complete")

    with col_right:
        # Determine Default Values
        d_name, d_obs, d_rec, d_sev = "", "", "", SEVERITY_LEVELS[0]
        
        # Priority: AI -> Library -> Empty
        if 'last_ai_res' in st.session_state and ai_res:
            lines = st.session_state['last_ai_res'].split('\n')
            for line in lines:
                if "Defect:" in line: d_name = line.replace("Defect:", "").strip()
                if "Observation:" in line: d_obs = line.replace("Observation:", "").strip()
                if "Recommendation:" in line: d_rec = line.replace("Recommendation:", "").strip()
        elif lib_prefill:
            d_name, d_obs, d_rec, d_sev = lib_prefill['name'], lib_prefill['obs'], lib_prefill['rec'], lib_prefill['sev']

        with st.form("defect_form", clear_on_submit=True):
            f_name = st.text_input("Defect Name", value=d_name)
            f_sev = st.selectbox("Severity", SEVERITY_LEVELS, index=SEVERITY_LEVELS.index(d_sev) if d_sev in SEVERITY_LEVELS else 0)
            f_obs = st.text_area("Observation", value=d_obs, height=100)
            f_rec = st.text_area("Recommendation", value=d_rec, height=100)
            
            if st.form_submit_button("Add to Report", use_container_width=True):
                st.session_state['inspection_data'].append({
                    "area": area, "defect_name": f_name, "observation": f_obs,
                    "severity": f_sev, "recommendation": f_rec
                })
                st.success("Entry Saved")

# --- PAGE: REPORT GENERATOR ---
def report_view():
    st.title("📄 Report Studio")
    
    if not st.session_state['inspection_data']:
        st.info("No defects logged. Go to 'New Inspection' to add items.")
        return

    # Editable Table
    st.markdown("### Review Findings")
    df = pd.DataFrame(st.session_state['inspection_data'])
    edited_df = st.data_editor(
        df, 
        use_container_width=True, 
        num_rows="dynamic",
        column_config={
            "severity": st.column_config.SelectboxColumn("Severity", options=SEVERITY_LEVELS)
        }
    )
    st.session_state['inspection_data'] = edited_df.to_dict('records')

    st.markdown("---")
    
    # PDF Action
    c1, c2 = st.columns([3, 1])
    with c1:
        if not st.session_state.get('prop_addr') or not st.session_state.get('client_nm'):
            st.warning("⚠️ Please enter Property Address and Client Name in the Inspection tab before downloading.")
        else:
            st.write("Ready to export.")
            
    with c2:
        if st.session_state.get('prop_addr') and st.session_state.get('client_nm'):
            pdf_bytes = generate_final_pdf(
                st.session_state['inspection_data'], 
                {"address": st.session_state.get('prop_addr'), "client": st.session_state.get('client_nm')},
                st.session_state['fullname'], 
                st.session_state.get('co_name', 'InspectPro'),
                st.session_state.get('lic_no', ''), 
                st.session_state.get('logo_file')
            )
            st.download_button(
                label="📥 Download PDF",
                data=pdf_bytes,
                file_name=f"Report_{st.session_state['client_nm']}.pdf",
                mime='application/pdf',
                type='primary',
                use_container_width=True
            )
    
    if st.button("🗑️ Clear All Data"):
        st.session_state['inspection_data'] = []
        st.rerun()

# --- PAGE: NEWS ---
def news_feed():
    st.title("🏗️ Industry Intelligence")
    st.write("Latest updates from Australian Construction sources.")
    
    feeds = ["https://www.architectureanddesign.com.au/rss"]
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                with st.container():
                    st.markdown(f"### [{entry.title}]({entry.link})")
                    st.caption(f"Published: {entry.get('published', 'Recent')}")
                    st.write(entry.get('summary', '')[:250] + "...")
        except:
            st.error("Could not load live feed.")

# --- PAGE: ADMIN ---
def admin_panel():
    st.title("🛡️ Admin Console")
    
    st.markdown("### User Management")
    users = get_all_users()
    st.dataframe(users, use_container_width=True, hide_index=True)
    
    st.markdown("### Add Inspector")
    with st.form("new_user"):
        c1, c2 = st.columns(2)
        u = c1.text_input("Username")
        p = c2.text_input("Password", type="password")
        f = st.text_input("Full Name")
        
        if st.form_submit_button("Create User"):
            if add_user(u, p, "Inspector", f):
                st.success("User Added Successfully")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Username already exists.")

# --- MAIN APP LOGIC ---
def main():
    init_db()
    apply_custom_css()
    
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'inspection_data' not in st.session_state: st.session_state['inspection_data'] = []
    if 'logo_file' not in st.session_state: st.session_state['logo_file'] = None

    if not st.session_state['logged_in']:
        login_page()
    else:
        page = sidebar_nav()
        if page == "Dashboard": dashboard()
        elif page == "New Inspection": inspection_form()
        elif page == "Report Generator": report_view()
        elif page == "Industry News": news_feed()
        elif page == "Admin Settings": admin_panel()

if __name__ == '__main__':
    main()
