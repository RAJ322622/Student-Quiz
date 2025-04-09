import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
import random
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase
from streamlit_autorefresh import st_autorefresh
import av

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
os.makedirs(RECORDING_DIR, exist_ok=True)

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
                        role TEXT DEFAULT 'student')''')
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
    role = st.selectbox("Role", ["student"])
    if st.button("Register"):
        register_user(username, password, role)

elif choice == "Login":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login successful!")

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        usn = st.text_input("Enter your USN")
        section = st.text_input("Enter your Section")
        st.session_state.usn = usn.strip().upper()
        st.session_state.section = section.strip().upper()

        if usn and section:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (username,))
            record = cur.fetchone()
            attempt_count = record[0] if record else 0

            if attempt_count >= 2:
                st.error("You have already taken the quiz 2 times. No more attempts allowed.")
            else:
                score = 0
                start_time = time.time()
                quiz_duration = 60  # seconds
                answers = {}
                shuffled_questions = random.sample(QUESTIONS, len(QUESTIONS))

                if not st.session_state.quiz_submitted and not st.session_state.camera_active:
                    add_active_student(username)
                    st.session_state.camera_active = True

                if st.session_state.camera_active and not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_streamer(
                        key="camera",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={"video": True, "audio": False},
                        video_processor_factory=VideoProcessor,
                    )

                remaining_time = quiz_duration - int(time.time() - start_time)
                if remaining_time <= 0:
                    st.error("Time is up! Please submit the quiz.")
                else:
                    st.info(f"⏳ Time remaining: {remaining_time} seconds")

                for idx, question in enumerate(shuffled_questions):
                    st.markdown(f"**Q{idx+1}:** {question['question']}")
                    ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                    answers[question['question']] = ans

                if st.button("Submit Quiz") and not st.session_state.quiz_submitted:
                    if None in answers.values():
                        st.error("Please answer all questions before submitting the quiz.")
                    else:
                        for q in shuffled_questions:
                            if answers.get(q["question"]) == q["answer"]:
                                score += 1
                        time_taken = round(time.time() - start_time, 2)

                        new_row = pd.DataFrame([[username, hash_password(username), st.session_state.usn, st.session_state.section, score, time_taken, datetime.now()]],
                                               columns=["Username", "Hashed_Password", "USN", "Section", "Score", "Time_Taken", "Timestamp"])

                        try:
                            old_df_prof = pd.read_csv(PROF_CSV_FILE)
                            full_df = pd.concat([old_df_prof, new_row], ignore_index=True)
                        except FileNotFoundError:
                            full_df = new_row
                        full_df.to_csv(PROF_CSV_FILE, index=False)

                        new_row[["Username", "USN", "Section", "Score", "Time_Taken", "Timestamp"]].to_csv(
                            STUDENT_CSV_FILE, mode='a', index=False, header=not os.path.exists(STUDENT_CSV_FILE)
                        )

                        section_csv = f"section_{st.session_state.section}.csv"
                        new_row.to_csv(section_csv, mode='a', index=False, header=not os.path.exists(section_csv))

                        st.success(f"Quiz submitted! Your score: {score}")

                        if record:
                            conn.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                        else:
                            conn.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, 1)", (username,))
                        conn.commit()

                        remove_active_student(username)
                        st.session_state.camera_active = False
                        st.session_state.quiz_submitted = True
            conn.close()

elif choice == "Professor Panel":
    st.header("Professor Panel")
    try:
        prof_df = pd.read_csv(PROF_CSV_FILE)
        st.dataframe(prof_df)
    except FileNotFoundError:
        st.warning("No quiz data available yet.")
