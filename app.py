# app.py
import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import requests
import pytz

# ---------- CONFIG ----------
FAST2SMS_API_KEY = "YOUR_FAST2SMS_API_KEY"  # <-- Replace with your Fast2SMS API key
REMINDER_DAYS_MIN = 5
REMINDER_DAYS_MAX = 10
IST = pytz.timezone("Asia/Kolkata")

# ---------- DATABASE SETUP ----------
conn = sqlite3.connect("members.db", check_same_thread=False)
c = conn.cursor()

# Users table (owner/staff)
c.execute("""CREATE TABLE IF NOT EXISTS users (
            name TEXT,
            phone TEXT PRIMARY KEY,
            role TEXT)""")

# Members table
c.execute("""CREATE TABLE IF NOT EXISTS members (
            name TEXT PRIMARY KEY,
            phone TEXT UNIQUE,
            plan TEXT,
            expiry_date TEXT,
            added_by_name TEXT,
            added_by_phone TEXT,
            created_time TEXT,
            reminder_sent INTEGER DEFAULT 0)""")
conn.commit()

# Add default users if not exist
def add_default_users():
    c.execute("SELECT * FROM users WHERE phone='OWNER001'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name,phone,role) VALUES (?,?,?)",
                  ('Owner','OWNER001','owner'))
    c.execute("SELECT * FROM users WHERE phone='STAFF001'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name,phone,role) VALUES (?,?,?)",
                  ('Staff','STAFF001','staff'))
    conn.commit()
add_default_users()

# ---------- SMS FUNCTION ----------
def send_sms(phone,message):
    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "sender_id":"FSTSMS",
        "message": message,
        "language":"english",
        "route":"q",
        "numbers": phone
    }
    headers = {
        "authorization": FAST2SMS_API_KEY,
        "Content-Type":"application/json"
    }
    try:
        response = requests.post(url,json=payload,headers=headers,timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def welcome_message(name,expiry):
    return f"🎉 Hi {name}, your membership is active till {expiry}. - [YourOrg]"

def reminder_message(name,expiry,days_left):
    return f"⚠️ Hi {name}, your membership expires on {expiry} ({days_left} days left). Renew now! - [YourOrg]"

# ---------- LOGIN ----------
st.set_page_config(page_title="Membership Manager", layout="wide")
st.title("Membership Management System")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.subheader("Login as Staff or Owner")
    phone_input = st.text_input("Your Staff/Owner Phone ID")
    role_input = st.selectbox("Role", ["staff","owner"])
    if st.button("Login"):
        c.execute("SELECT name FROM users WHERE phone=? AND role=?", (phone_input,role_input))
        res = c.fetchone()
        if res:
            st.session_state['logged_in'] = True
            st.session_state['name'] = res[0]
            st.session_state['phone'] = phone_input
            st.session_state['role'] = role_input
            st.success(f"Logged in as {res[0]} ({role_input})")
        else:
            st.error("Invalid credentials")
    st.stop()

# ---------- MAIN APP ----------
role = st.session_state['role']
staff_name = st.session_state['name']
staff_phone = st.session_state['phone']

st.sidebar.write(f"Logged in: {staff_name} ({role})")

# ---------- ADD MEMBER ----------
st.subheader("Add New Member")
with st.form("add_member", clear_on_submit=True):
    name = st.text_input("Member Name")
    phone = st.text_input("Member Phone (+91XXXXXXXXXX)")
    plan = st.text_input("Plan/Package")
    expiry = st.date_input("Expiry Date")
    submitted = st.form_submit_button("Submit")
    
    if submitted:
        if not name or not phone:
            st.error("Name and Phone required!")
        else:
            # check duplicates
            c.execute("SELECT * FROM members WHERE name=? OR phone=?", (name,phone))
            if c.fetchone():
                st.error("Member with this Name or Phone already exists!")
            elif expiry < datetime.now(IST).date():
                st.error("Expiry must be today or future date!")
            else:
                created_time = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p")
                c.execute("""INSERT INTO members 
                             (name,phone,plan,expiry_date,added_by_name,added_by_phone,created_time)
                             VALUES (?,?,?,?,?,?,?)""",
                          (name,phone,plan,expiry.isoformat(),staff_name,staff_phone,created_time))
                conn.commit()
                st.success(f"Member '{name}' added successfully!")
                # Send welcome SMS
                msg = welcome_message(name, expiry.strftime("%d-%b-%Y"))
                send_sms(phone,msg)

# ---------- VIEW MEMBERS ----------
st.subheader("Members List")
df = pd.read_sql("SELECT * FROM members", conn)
if not df.empty:
    df['expiry_date'] = pd.to_datetime(df['expiry_date']).dt.date
    df['days_left'] = df['expiry_date'].apply(lambda d: (d - datetime.now(IST).date()).days)
    st.dataframe(df.sort_values("expiry_date"))
else:
    st.info("No members yet.")

# ---------- AUTOMATIC REMINDERS ----------
st.subheader("Automatic Reminder SMS (5–10 days before expiry)")
for index,row in df.iterrows():
    if REMINDER_DAYS_MIN <= row['days_left'] <= REMINDER_DAYS_MAX and row['reminder_sent']==0:
        msg = reminder_message(row['name'],row['expiry_date'].strftime("%d-%b-%Y"),row['days_left'])
        send_sms(row['phone'],msg)
        c.execute("UPDATE members SET reminder_sent=1 WHERE name=?", (row['name'],))
conn.commit()
st.success("Reminders sent automatically for members expiring soon!")

# ---------- OWNER CONTROLS ----------
if role=="owner":
    st.subheader("Owner Controls")
    edit_name = st.text_input("Enter Member Name to Delete or Update Plan")
    new_plan = st.text_input("New Plan (if updating)")
    if st.button("Delete Member"):
        c.execute("DELETE FROM members WHERE name=?", (edit_name,))
        conn.commit()
        st.success(f"Deleted member {edit_name}")
    if st.button("Update Plan"):
        c.execute("UPDATE members SET plan=? WHERE name=?", (new_plan,edit_name))
        conn.commit()
        st.success(f"Updated plan for {edit_name}")
