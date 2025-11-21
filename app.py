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
    page_title="Inspect Yourself | Pro",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    "Garage/Carport"
]

# Library of common defects to speed up reporting (Competitor Feature)
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
    """Initialize SQLite DB and create default admin if missing."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, full_name TEXT)''')
    
    # Check for admin
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        # Hash for 'inspect'
        # Calculated via hashlib.sha256(b"inspect").hexdigest()
        secure_pass = "9b8769a4a742959a2d0299c36cc16350aa06eb49dc97281c9bf63f448f35796c"
        c.execute("INSERT INTO users VALUES ('admin', ?, 'admin', 'Principal Inspector')", (secure_pass,))
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

def delete_user_db(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()

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
        # Logo
        if self.logo_path:
            try:
                # 10, 8 is x, y position. 33 is width.
                self.image(self.logo_path, 10, 8, 33)
            except:
                pass # Fail silently if logo file issue
                
        self.set_font('Arial', 'B', 16)
        # Move to right for title if logo exists
        if self.logo_path:
            self.cell(40)
        
        self.cell(0, 10, f'{self.company_name} - Inspection Report', 0, 1, 'L')
        
        if self.logo_path:
            self.cell(40)
        self.set_font('Arial', '', 10)
        self.cell(0, 5, f'Licence No: {self.license_no} | Compliant with AS 4349.1-2007', 0, 1, 'L')
        self.ln(10)
        # Line break
        self.line(10, 30, 200, 30)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Generated by Inspect Yourself | Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 6, label, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, body)
        self.ln()

def generate_final_pdf(report_data, prop_details, inspector, company, license_num, logo_file):
    # Handle Logo Temp File
    logo_path = None
    if logo_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(logo_file.getvalue())
            logo_path = tmp.name

    pdf = InspectionPDF(company, license_num, logo_path)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 1. Property Details
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Property Inspection Details", 0, 1)
    pdf.set_font('Arial', '', 11)
    
    details = [
        f"Address: {prop_details['address']}",
        f"Client: {prop_details['client']}",
        f"Inspection Date: {datetime.now().strftime('%d %B %Y')}",
        f"Inspector: {inspector}",
        f"Weather Conditions: {prop_details.get('weather', 'Not Recorded')}"
    ]
    
    for det in details:
        pdf.cell(0, 7, det, 0, 1)
    pdf.ln(5)

    # 2. Executive Summary (Stats)
    pdf.chapter_title("Executive Summary")
    minor_count = len([x for x in report_data if "Minor" in x['severity']])
    major_count = len([x for x in report_data if "Major" in x['severity']])
    safety_count = len([x for x in report_data if "Safety" in x['severity']])
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(60, 10, f"Major Defects Found: {major_count}", 1)
    pdf.cell(60, 10, f"Safety Hazards: {safety_count}", 1)
    pdf.cell(60, 10, f"Minor Defects: {minor_count}", 1)
    pdf.ln(15)

    # 3. Defect Details
    pdf.chapter_title("Defect Findings")
    
    if not report_data:
        pdf.cell(0, 10, "No significant defects recorded during this inspection.", 0, 1)
    
    for item in report_data:
        # Title Bar for Defect
        pdf.set_font('Arial', 'B', 11)
        # Color code based on severity
        if "Safety" in item['severity']:
            pdf.set_text_color(200, 0, 0) # Red
        elif "Major" in item['severity']:
            pdf.set_text_color(200, 100, 0) # Orange
        else:
            pdf.set_text_color(0, 0, 100) # Dark Blue
            
        pdf.cell(0, 8, f"{item['area']} | {item['defect_name']}", 0, 1)
        pdf.set_text_color(0) # Reset
        
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(25, 5, "Severity:", 0)
        pdf.set_font('Arial', '', 9)
        pdf.cell(0, 5, item['severity'], 0, 1)
        
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(25, 5, "Observation:", 0)
        pdf.set_font('Arial', '', 9)
        pdf.multi_cell(0, 5, item['observation'])
        
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(25, 5, "Advice:", 0)
        pdf.set_font('Arial', '', 9)
        pdf.multi_cell(0, 5, item['recommendation'])
        
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    # 4. Terms & Conditions (Legal)
    pdf.add_page()
    pdf.chapter_title("Terms, Conditions & Limitations")
    disclaimer = """
    1. SCOPE: This report is a Visual Inspection only, carried out in accordance with AS 4349.1-2007. The inspection covers only safe and accessible areas.
    
    2. LIMITATIONS: The inspector did not dismantle, move objects, or cut into walls/floors. Concealed defects (e.g., behind furniture, within walls) are not reported. Plumbing and electrical systems were checked for visible defects only; no license compliance certification is implied.
    
    3. EXCLUSIONS: This report does not cover asbestos, mould (unless specified), soil toxicity, or council compliance. 
    
    4. SAFETY: Any safety hazards noted should be addressed immediately by a qualified professional.
    
    5. COPYRIGHT: This report is for the exclusive use of the Client named on the front page.
    """
    pdf.set_font('Arial', '', 8)
    pdf.multi_cell(0, 4, disclaimer)

    # Clean up temp file
    if logo_path and os.path.exists(logo_path):
        os.unlink(logo_path)

    return pdf.output(dest='S').encode('latin-1')

# --- UI SECTIONS ---

def login_page():
    st.markdown("""
    <style>
        .stApp { background-color: #e0e5eb; }
        .login-container { max-width: 400px; margin: auto; padding-top: 50px; }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("Inspect Yourself")
        st.caption("Professional Building Inspection Suite")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)
            
            if submit:
                user = check_login(username, password)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.session_state['role'] = user[0]
                    st.session_state['fullname'] = user[1]
                    st.rerun()
                else:
                    st.error("Access Denied.")
        
        st.info("First Time? Use: admin / inspect")

def sidebar_settings():
    with st.sidebar:
        st.title("Settings ⚙️")
        
        with st.expander("Company Branding", expanded=True):
            st.session_state['co_name'] = st.text_input("Company Name", value=st.session_state.get('co_name', 'My Inspection Co'))
            st.session_state['lic_no'] = st.text_input("License Number", value=st.session_state.get('lic_no', 'AU-12345'))
            
            # Logo Upload
            uploaded_logo = st.file_uploader("Report Logo (PNG/JPG)", type=['png', 'jpg', 'jpeg'])
            if uploaded_logo:
                st.session_state['logo_file'] = uploaded_logo
                st.image(uploaded_logo, width=100)
        
        with st.expander("AI Configuration"):
            api_key = st.text_input("Gemini API Key", type="password", value=st.session_state.get('api_key', ''))
            if api_key:
                st.session_state['api_key'] = api_key
            st.caption("Required for Photo Analysis")
        
        if st.button("Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

def tab_inspection():
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.subheader("📍 Property & Scope")
        with st.container(border=True):
            c1, c2 = st.columns(2)
            st.session_state['prop_addr'] = c1.text_input("Address", st.session_state.get('prop_addr', ''))
            st.session_state['client_nm'] = c2.text_input("Client Name", st.session_state.get('client_nm', ''))
            st.session_state['weather'] = st.text_input("Weather Conditions", st.session_state.get('weather', 'Fine & Sunny'))

        st.subheader("📝 Defect Log")
        
        # 1. Select Area
        area = st.selectbox("Area Inspected", AREAS)
        
        # 2. Auto-fill from Library (Feature from Competitors)
        use_lib = st.checkbox("Use Defect Library")
        lib_selection = None
        
        pre_name, pre_obs, pre_rec, pre_sev = "", "", "", SEVERITY_LEVELS[0]
        
        if use_lib and area in COMMON_DEFECTS:
            defect_names = [d['name'] for d in COMMON_DEFECTS[area]]
            selected_def_name = st.selectbox("Quick Select Defect", defect_names)
            # Find data
            lib_data = next(item for item in COMMON_DEFECTS[area] if item["name"] == selected_def_name)
            pre_name = lib_data['name']
            pre_obs = lib_data['obs']
            pre_rec = lib_data['rec']
            pre_sev = lib_data['sev']

        # 3. AI Analysis
        uploaded_photo = st.file_uploader("Upload Photo Evidence", type=['jpg', 'png', 'jpeg'])
        if uploaded_photo and st.session_state.get('api_key'):
            if st.button("🤖 Ask AI to Analyze"):
                with st.spinner("AI Inspector is reviewing..."):
                    img = Image.open(uploaded_photo)
                    result = analyze_image_with_ai(img, st.session_state['api_key'])
                    
                    # Attempt to parse AI result
                    lines = result.split('\n')
                    for line in lines:
                        if "Defect:" in line: pre_name = line.replace("Defect:", "").strip()
                        if "Observation:" in line: pre_obs = line.replace("Observation:", "").strip()
                        if "Recommendation:" in line: pre_rec = line.replace("Recommendation:", "").strip()
                        if "Severity:" in line: 
                            # Try to match severity
                            ai_sev = line.replace("Severity:", "").strip()
                            for s in SEVERITY_LEVELS:
                                if ai_sev.split()[0] in s: # Match 'Minor', 'Major'
                                    pre_sev = s
                    st.success("AI Suggestions Applied below!")

        # 4. Input Form (Pre-filled by Library or AI)
        with st.form("entry_form", clear_on_submit=True):
            d_name = st.text_input("Defect Title", value=pre_name)
            d_obs = st.text_area("Observation", value=pre_obs)
            d_sev = st.selectbox("Severity", SEVERITY_LEVELS, index=SEVERITY_LEVELS.index(pre_sev) if pre_sev in SEVERITY_LEVELS else 0)
            d_rec = st.text_area("Recommendation", value=pre_rec)
            
            added = st.form_submit_button("Add to Report")
            if added:
                st.session_state['inspection_data'].append({
                    "area": area,
                    "defect_name": d_name,
                    "observation": d_obs,
                    "severity": d_sev,
                    "recommendation": d_rec
                })
                st.success("Defect Logged")

    with col2:
        st.info("Current Session Statistics")
        if 'inspection_data' in st.session_state:
            cnt = len(st.session_state['inspection_data'])
            st.metric("Defects Logged", cnt)
        else:
            st.metric("Defects Logged", 0)
            
        st.markdown("### Recent Entries")
        if st.session_state['inspection_data']:
            # Show brief list
            for i, d in enumerate(st.session_state['inspection_data'][-3:]):
                st.text(f"{d['area']}: {d['defect_name']}")
        else:
            st.caption("No entries yet.")

def tab_report():
    st.subheader("🔍 Review & Edit Report")
    
    if st.session_state['inspection_data']:
        # Editable Dataframe (Pro Feature)
        df = pd.DataFrame(st.session_state['inspection_data'])
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        
        # Sync changes back
        st.session_state['inspection_data'] = edited_df.to_dict('records')
        
        st.divider()
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🗑️ Clear Entire Report"):
                st.session_state['inspection_data'] = []
                st.rerun()
        
        with col_b:
            if st.session_state.get('prop_addr') and st.session_state.get('client_nm'):
                try:
                    pdf_data = generate_final_pdf(
                        st.session_state['inspection_data'],
                        {
                            "address": st.session_state.get('prop_addr'), 
                            "client": st.session_state.get('client_nm'),
                            "weather": st.session_state.get('weather')
                        },
                        st.session_state['fullname'],
                        st.session_state.get('co_name', 'Inspection Co'),
                        st.session_state.get('lic_no', 'N/A'),
                        st.session_state.get('logo_file')
                    )
                    
                    st.download_button(
                        label="📄 Download Professional PDF",
                        data=pdf_data,
                        file_name=f"Report_{st.session_state['client_nm']}.pdf",
                        mime='application/pdf',
                        type='primary'
                    )
                except Exception as e:
                    st.error(f"PDF Generation Error: {e}")
            else:
                st.warning("Please fill in Property Address and Client Name in the 'Inspection' tab to generate PDF.")
    else:
        st.info("No data to report. Go to the Inspection tab to start logging.")

def tab_news():
    st.subheader("Industry News (Australia)")
    feeds = ["https://www.architectureanddesign.com.au/rss"]
    
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                st.markdown(f"**[{entry.title}]({entry.link})**")
                st.caption(entry.get('published', ''))
                st.write(entry.get('summary', '')[:200] + "...")
                st.divider()
        except:
            st.error("Unable to fetch news feed.")

def tab_admin():
    st.subheader("User Management")
    
    users = get_all_users()
    st.dataframe(users, use_container_width=True)
    
    with st.form("add_user"):
        st.write("Create New Inspector")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        f = st.text_input("Full Name")
        r = st.selectbox("Role", ["Inspector", "Admin"])
        if st.form_submit_button("Create"):
            if add_user(u, p, r, f):
                st.success("User Created")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Username exists")

    st.divider()
    st.write("Delete User")
    u_del = st.selectbox("Select User", users['username'].tolist())
    if st.button("Delete Selected"):
        if u_del == 'admin':
            st.error("Cannot delete Root Admin")
        else:
            delete_user_db(u_del)
            st.success("Deleted")
            time.sleep(1)
            st.rerun()

# --- MAIN LOGIC ---
def main():
    init_db()
    
    # Initialize Session State
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'inspection_data' not in st.session_state:
        st.session_state['inspection_data'] = []
    if 'logo_file' not in st.session_state:
        st.session_state['logo_file'] = None

    if not st.session_state['logged_in']:
        login_page()
    else:
        sidebar_settings()
        
        # Tab Structure
        t1, t2, t3, t4 = st.tabs(["🏗️ Inspection", "📄 Review & Export", "📰 News", "🛡️ Admin"])
        
        with t1:
            tab_inspection()
        with t2:
            tab_report()
        with t3:
            tab_news()
        with t4:
            if st.session_state['role'] == 'admin':
                tab_admin()
            else:
                st.warning("Restricted Area. Admins only.")

if __name__ == '__main__':
    main()