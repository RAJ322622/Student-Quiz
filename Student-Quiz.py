import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
import requests
import random
import string
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase
from streamlit_autorefresh import st_autorefresh
import av

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
os.makedirs(RECORDING_DIR, exist_ok=True)

# Email API details (you can use services like EmailAPI.io or Mailjet)
EMAIL_API_URL = "https://api.emailapi.io/v1/send"  # replace with real API
EMAIL_API_KEY = "your_api_key_here"  # replace with real API key
SENDER_EMAIL = "rajkumar.b6303@gmail.com"  # replace with your verified email

# Email sender
def send_email(to, subject, message):
    try:
        payload = {
            "api_key": EMAIL_API_KEY,
            "to": to,
            "sender": SENDER_EMAIL,
            "subject": subject,
            "body": message
        }
        response = requests.post(EMAIL_API_URL, json=payload)
        return response.status_code == 200
    except Exception as e:
        st.warning("Email sending failed.")
        return False

# Session state defaults
for key in ["logged_in", "username", "camera_active", "prof_verified", "quiz_submitted", "usn", "section"]:
    if key not in st.session_state:
        st.session_state[key] = False if key not in ["username", "usn", "section"] else ""

# DB connection
def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT,
                        role TEXT DEFAULT 'student',
                        email TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                        username TEXT PRIMARY KEY,
                        change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                        username TEXT PRIMARY KEY,
                        attempt_count INTEGER DEFAULT 0)''')
    return conn

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Register user
def register_user(username, password, role, email):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                     (username, hash_password(password), role, email))
        conn.commit()
        st.success("Registration successful! Please login.")
        # Send welcome email
        msg = f"Dear {username},\n\nWelcome to the Secure Quiz App.\nYour account has been registered successfully.\n\nRegards,\nTeam"
        send_email(email, "Registration Successful", msg)
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    conn.close()

# Authenticate user
def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and user[0] == hash_password(password)

# Get user role
def get_user_role(username):
    conn = get_db_connection()
    cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
    role = cursor.fetchone()
    conn.close()
    return role[0] if role else "student"

# Active student tracking
def add_active_student(username):
    try:
        with open(ACTIVE_FILE, "r") as f:
            data = json.load(f)
    except:
        data = []
    if username not in data:
        data.append(username)
        with open(ACTIVE_FILE, "w") as f:
            json.dump(data, f)

def remove_active_student(username):
    try:
        with open(ACTIVE_FILE, "r") as f:
            data = json.load(f)
        data = [u for u in data if u != username]
        with open(ACTIVE_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass

def get_live_students():
    try:
        with open(ACTIVE_FILE, "r") as f:
            return json.load(f)
    except:
        return []

# Forgot password
def reset_password(username):
    conn = get_db_connection()
    cur = conn.execute("SELECT email FROM users WHERE username = ?", (username,))
    result = cur.fetchone()
    if result:
        email = result[0]
        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        conn.execute("UPDATE users SET password = ? WHERE username = ?", (hash_password(new_password), username))
        conn.commit()
        send_email(email, "Password Reset", f"Hello {username},\n\nYour new password is: {new_password}\n\nPlease change it after login.")
        st.success("A new password has been sent to your registered email.")
    else:
        st.error("Username not found.")
    conn.close()

# Dummy question bank
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

# Video processor
class VideoProcessor(VideoTransformerBase):
    def recv(self, frame):
        return frame

# UI Starts
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    email = st.text_input("Email")
    role = st.selectbox("Role", ["student"])
    if st.button("Register"):
        register_user(username, password, role, email)

elif choice == "Login":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login successful!")
    if st.button("Forgot Password?"):
        if username:
            reset_password(username)
        else:
            st.warning("Enter your username to reset password.")
# Add this after the Login block in your code:

elif choice == "Take Quiz" and st.session_state.logged_in:
    st.subheader("Take Quiz")

    if not st.session_state.quiz_submitted:
        st.session_state.usn = st.text_input("Enter your USN:")
        st.session_state.section = st.text_input("Enter your Section:")
        st_autorefresh(interval=1000 * 60, limit=25, key="quiz_refresh")  # 25-minute auto-refresh

        webrtc_streamer(key="camera", mode=WebRtcMode.SENDONLY, video_processor_factory=VideoProcessor)
        st.session_state.camera_active = True

        conn = get_db_connection()
        cur = conn.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (st.session_state.username,))
        row = cur.fetchone()
        attempt_count = row[0] if row else 0

        if attempt_count >= 2:
            st.warning("You have exceeded the allowed number of quiz attempts.")
        else:
            answers = {}
            for i, q in enumerate(QUESTIONS):
                st.write(f"Q{i+1}. {q['question']}")
                answers[i] = st.radio(f"Select Answer for Q{i+1}", q["options"], key=f"q{i}")

            if st.button("Submit Quiz"):
                score = sum(1 for i, q in enumerate(QUESTIONS) if answers.get(i) == q["answer"])
                result_data = {
                    "Username": st.session_state.username,
                    "USN": st.session_state.usn,
                    "Section": st.session_state.section,
                    "Score": score,
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                filename = f"{st.session_state.section}_results.csv"
                file_exists = os.path.isfile(filename)
                with open(filename, "a") as f:
                    if not file_exists:
                        f.write("Username,USN,Section,Score,Date\n")
                    f.write(",".join(map(str, result_data.values())) + "\n")

                conn.execute("INSERT OR REPLACE INTO quiz_attempts (username, attempt_count) VALUES (?, ?)",
                             (st.session_state.username, attempt_count + 1))
                conn.commit()
                st.success(f"Quiz submitted! Score: {score}/" + str(len(QUESTIONS)))
                st.session_state.quiz_submitted = True
                st.session_state.camera_active = False
        conn.close()

elif choice == "Change Password" and st.session_state.logged_in:
    st.subheader("Change Password")
    old = st.text_input("Old Password", type="password")
    new = st.text_input("New Password", type="password")
    confirm = st.text_input("Confirm New Password", type="password")

    if st.button("Update Password"):
        conn = get_db_connection()
        cur = conn.execute("SELECT password FROM users WHERE username = ?", (st.session_state.username,))
        row = cur.fetchone()
        if row and row[0] == hash_password(old):
            cur = conn.execute("SELECT change_count FROM password_changes WHERE username = ?", (st.session_state.username,))
            count_row = cur.fetchone()
            change_count = count_row[0] if count_row else 0
            if change_count >= 2:
                st.warning("Password change limit exceeded.")
            elif new != confirm:
                st.warning("New passwords do not match.")
            else:
                conn.execute("UPDATE users SET password = ? WHERE username = ?", (hash_password(new), st.session_state.username))
                conn.execute("INSERT OR REPLACE INTO password_changes (username, change_count) VALUES (?, ?)",
                             (st.session_state.username, change_count + 1))
                conn.commit()
                st.success("Password updated.")
        else:
            st.warning("Old password is incorrect.")
        conn.close()

elif choice == "Professor Panel" and st.session_state.logged_in:
    st.subheader("Professor Panel")
    section = st.text_input("Enter section to view results")
    if st.button("Load Results"):
        filename = f"{section}_results.csv"
        if os.path.isfile(filename):
            df = pd.read_csv(filename)
            st.dataframe(df)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, file_name=f"{section}_results.csv")
        else:
            st.warning("No results found for this section.")

elif choice == "Professor Monitoring Panel" and st.session_state.logged_in:
    st.subheader("Professor Monitoring Panel")
    live = get_live_students()
    if live:
        st.write("Live Students Writing the Quiz:")
        for student in live:
            st.write(f"- {student}")
    else:
        st.info("No students are currently writing the quiz.")

elif choice == "View Recorded Video" and st.session_state.logged_in:
    st.subheader("Recorded Webcam Video")
    recordings = os.listdir(RECORDING_DIR)
    user_videos = [f for f in recordings if f.startswith(st.session_state.username)]
    if user_videos:
        for video_file in user_videos:
            st.video(os.path.join(RECORDING_DIR, video_file))
    else:
        st.info("No recordings found.")


# All other code remains exactly as you already have it (Take Quiz, Change Password, Professor Panel, etc.)
# You can paste your existing blocks below this line.

