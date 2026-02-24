import streamlit as st
import sqlite3
import bcrypt
import requests
from bs4 import BeautifulSoup
from keybert import KeyBERT

# ------------------------------
# DATABASE SETUP
# ------------------------------
conn = sqlite3.connect("sastra_users.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    password_hash BLOB,
    scopus_id TEXT,
    orcid_id TEXT,
    scholar_link TEXT,
    researchgate_link TEXT,
    faculty_url TEXT
)
""")
conn.commit()

# ------------------------------
# SESSION STATE
# ------------------------------
if "page" not in st.session_state:
    st.session_state.page = "login"
if "email" not in st.session_state:
    st.session_state.email = None

# ------------------------------
# UTILITY FUNCTIONS
# ------------------------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

def extract_keywords(text):
    model = KeyBERT()
    keywords = model.extract_keywords(text, top_n=6)
    return [kw[0] for kw in keywords]

# ------------------------------
# SCRAPER FUNCTION
# ------------------------------
def scrape_sastra_faculty(url, user_email):
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        faculty_blocks = soup.find_all("h1")
        username = user_email.split("@")[0].lower()
        for prof in faculty_blocks:
            name = prof.get_text(strip=True)
            if username in name.lower().replace(" ", ""):
                parent = prof.find_next_sibling()
                text = ""
                while parent and parent.name != "h1":
                    text += parent.get_text(separator=" ", strip=True) + " "
                    parent = parent.find_next_sibling()
                # Areas of Interest
                areas = ""
                if "Areas of Interest" in text:
                    areas = text.split("Areas of Interest")[1]
                    areas = areas.split("ORCID")[0].strip() if "ORCID" in areas else areas.strip()
                # ORCID
                orcid_tag = prof.find_next("a", href=True)
                orcid = ""
                if orcid_tag and "orcid.org" in orcid_tag["href"]:
                    orcid = orcid_tag["href"]
                research_summary = f"Research focused on {areas} with interdisciplinary applications." if areas else "Research summary not found."
                h_index = "Not Available"
                return {
                    "name": name,
                    "research_summary": research_summary,
                    "areas_of_interest": areas,
                    "orcid_id": orcid,
                    "h_index": h_index
                }
        return {"error": "Faculty profile not found for this email."}
    except Exception as e:
        return {"error": str(e)}

# ------------------------------
# PAGE 1 — LOGIN
# ------------------------------
if st.session_state.page == "login":
    st.title("SASTRA Faculty Login")
    email = st.text_input("University Email")

    if st.button("Continue"):
        if not email.lower().endswith("@sastra.edu"):
            st.error("Access restricted to SASTRA University faculty.")
        else:
            st.session_state.email = email.lower()
            c.execute("SELECT * FROM users WHERE email=?", (st.session_state.email,))
            user = c.fetchone()
            if user:
                st.session_state.page = "signin"
            else:
                st.session_state.page = "set_password"
            st.rerun()

# ------------------------------
# PAGE 2 — SET PASSWORD
# ------------------------------
elif st.session_state.page == "set_password":
    st.title("Set Password")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm Password", type="password")

    if st.button("Register"):
        if password != confirm:
            st.error("Passwords do not match.")
        elif len(password) < 8:
            st.error("Password must be at least 8 characters.")
        else:
            hashed = hash_password(password)
            c.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                      (st.session_state.email, hashed))
            conn.commit()
            st.success("Password set successfully.")
            st.session_state.page = "academic_id"
            st.rerun()

# ------------------------------
# PAGE 3 — SIGN IN
# ------------------------------
elif st.session_state.page == "signin":
    st.title("Sign In")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        c.execute("SELECT password_hash FROM users WHERE email=?",
                  (st.session_state.email,))
        stored = c.fetchone()
        if stored and check_password(password, stored[0]):
            st.success("Login successful")
            st.session_state.page = "academic_id"
            st.rerun()
        else:
            st.error("Invalid password")

# ------------------------------
# PAGE 4 — ACADEMIC ID VERIFICATION
# ------------------------------
elif st.session_state.page == "academic_id":
    st.title("Academic Profile Verification")
    scopus_id = st.text_input("Scopus ID (Mandatory)")
    orcid_id = st.text_input("ORCID ID (Optional)")
    scholar_link = st.text_input("Google Scholar Link (Optional)")
    researchgate_link = st.text_input("ResearchGate Link (Optional)")
    faculty_url = st.text_input("Faculty Profile URL (Mandatory)")

    if st.button("Submit"):
        if not scopus_id:
            st.error("Scopus ID is mandatory.")
        elif not (orcid_id or scholar_link or researchgate_link):
            st.error("Provide at least one academic profile ID.")
        elif not faculty_url:
            st.error("Faculty profile URL is required.")
        else:
            c.execute("""
            UPDATE users SET
                scopus_id=?,
                orcid_id=?,
                scholar_link=?,
                researchgate_link=?,
                faculty_url=?
            WHERE email=?
            """, (scopus_id, orcid_id, scholar_link, researchgate_link, faculty_url, st.session_state.email))
            conn.commit()
            st.session_state.page = "dashboard"
            st.rerun()

# ------------------------------
# PAGE 5 — DASHBOARD
# ------------------------------
elif st.session_state.page == "dashboard":
    st.title("Faculty Profile Dashboard")
    c.execute("SELECT faculty_url FROM users WHERE email=?",
              (st.session_state.email,))
    faculty_url = c.fetchone()[0]
    profile = scrape_sastra_faculty(faculty_url, st.session_state.email)

    if "error" not in profile:
        st.subheader("Name:")
        st.write(profile["name"])
        st.subheader("Research Summary:")
        st.write(profile["research_summary"])
        st.subheader("Suggested Keywords for Collaboration Finder:")
        keywords = extract_keywords(profile["research_summary"])
        for kw in keywords:
            st.write("•", kw)
        st.subheader("H-index:")
        st.write(profile["h_index"])
    else:
        st.error(profile["error"])

    if st.button("Logout"):
        st.session_state.page = "login"
        st.session_state.email = None
        st.rerun()
