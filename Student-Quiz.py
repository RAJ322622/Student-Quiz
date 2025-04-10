import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from streamlit_webrtc import WebRtcMode
from streamlit_autorefresh import st_autorefresh
import cv2

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
IMAGE_DIR = "video_recorder"
os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

for key in ["logged_in", "username", "camera_active", "prof_verified", "quiz_submitted", "usn", "section", "email"]:
    if key not in st.session_state:
        st.session_state[key] = False if key not in ["username", "usn", "section", "email"] else ""

def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT,
                        role TEXT DEFAULT 'student')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                        username TEXT PRIMARY KEY,
                        change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                        username TEXT PRIMARY KEY,
                        attempt_count INTEGER DEFAULT 0)''')
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     (username, hash_password(password), role))
        conn.commit()
        st.success("Registration successful! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    conn.close()

def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and user[0] == hash_password(password)

def get_user_role(username):
    conn = get_db_connection()
    cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
    role = cursor.fetchone()
    conn.close()
    return role[0] if role else "student"

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

QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

def capture_image(username):
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    if ret:
        filename = os.path.join(IMAGE_DIR, f"{username}_{int(time.time())}.png")
        cv2.imwrite(filename, frame)
    cap.release()

EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"

def send_email(recipient, subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = recipient
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False

st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Create a New Account")
    new_user = st.text_input("Username")
    new_pass = st.text_input("Password", type="password")
    role = st.radio("Register as", ["student", "professor"])
    if st.button("Register"):
        if new_user and new_pass:
            register_user(new_user, new_pass, role)
        else:
            st.warning("Please enter both username and password.")

elif choice == "Login":
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.success("Login successful!")
            st.session_state.logged_in = True
            st.session_state.username = username
            user_role = get_user_role(username)
            st.session_state.prof_verified = user_role == "professor"
        else:
            st.error("Invalid username or password.")

elif choice == "Professor Panel":
    if not st.session_state.logged_in or not st.session_state.prof_verified:
        st.warning("Access restricted to professors only. Please login as a professor.")
    else:
        st.subheader("Professor Quiz Submissions Panel")
        try:
            df = pd.read_csv(PROF_CSV_FILE)
            st.dataframe(df)
        except FileNotFoundError:
            st.warning("No quiz results available yet.")

elif choice == "Professor Monitoring Panel":
    if not st.session_state.logged_in or not st.session_state.prof_verified:
        st.warning("Access restricted to professors only. Please login as a professor.")
    else:
        st.subheader("Live Student Monitoring")
        students = get_live_students()
        if students:
            st.write("Active Students:", students)
        else:
            st.info("No active students currently taking the quiz.")

elif choice == "View Recorded Video":
    st.subheader("Captured Webcam Images")
    images = os.listdir(IMAGE_DIR)
    if not images:
        st.info("No captured images available.")
    else:
        selected_user = st.selectbox("Select a User", list(set(name.split("_")[0] for name in images)))
        user_images = [img for img in images if img.startswith(selected_user)]
        for img_file in sorted(user_images):
            img_path = os.path.join(IMAGE_DIR, img_file)
            st.image(img_path, caption=img_file)

if choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        # Quiz logic continues...
        pass
