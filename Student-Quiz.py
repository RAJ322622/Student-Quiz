import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"

# Session state defaults
for key in ["logged_in", "username", "camera_active", "prof_verified", "quiz_submitted"]:
    if key not in st.session_state:
        st.session_state[key] = False if key != "username" else ""

# Database connection
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

# Questions
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

# UI
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel"]
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
        else:
            st.error("Invalid credentials!")

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        score = 0
        start_time = time.time()
        answers = {}

        if not st.session_state.quiz_submitted:
            add_active_student(username)
            st.session_state.camera_active = True

        if st.session_state.camera_active and not st.session_state.quiz_submitted:
            st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
            webrtc_streamer(
                key="quiz_camera_hidden",
                mode=WebRtcMode.SENDRECV,
                media_stream_constraints={"video": True, "audio": False},
                video_html_attrs={
                    "style": {
                        "width": "0px",
                        "height": "0px",
                        "opacity": "0.01",
                        "position": "absolute",
                        "top": "0px",
                        "left": "0px",
                        "z-index": "-1"
                    }
                }
            )

        for idx, question in enumerate(QUESTIONS):
            st.markdown(f"**Q{idx+1}:** {question['question']}")
            ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
            answers[question['question']] = ans

        if st.button("Submit Quiz") and not st.session_state.quiz_submitted:
            for q in QUESTIONS:
                if answers.get(q["question"]) == q["answer"]:
                    score += 1
            time_taken = round(time.time() - start_time, 2)

            new_row = pd.DataFrame([[username, hash_password(username), score, time_taken, datetime.now()]],
                                   columns=["Username", "Hashed_Password", "Score", "Time_Taken", "Timestamp"])

            try:
                old_df_prof = pd.read_csv(PROF_CSV_FILE)
                full_df = pd.concat([old_df_prof, new_row], ignore_index=True)
            except FileNotFoundError:
                full_df = new_row
            full_df.to_csv(PROF_CSV_FILE, index=False)

            new_row[["Username", "Score", "Time_Taken", "Timestamp"]].to_csv(
                STUDENT_CSV_FILE, mode='a', index=False, header=not os.path.exists(STUDENT_CSV_FILE)
            )

            st.success(f"Quiz submitted! Your score: {score}")

            remove_active_student(username)
            st.session_state.camera_active = False
            st.session_state.quiz_submitted = True
            st.experimental_set_query_params()

elif choice == "Professor Panel":
    st.subheader("\U0001F9D1‍\U0001F3EB Professor Access Panel")
    if not st.session_state.prof_verified:
        prof_user = st.text_input("Professor Username")
        prof_pass = st.text_input("Professor Password", type="password")
        if st.button("Verify Professor"):
            if prof_user.strip().lower() == "raj kumar" and prof_pass.strip().lower() == "raj kumar":
                st.session_state.prof_verified = True
                st.success("Professor verified! You can now access results.")
            else:
                st.error("Access denied. Invalid professor credentials.")
    else:
        st.success("Welcome Professor Raj Kumar!")
        if os.path.exists(PROF_CSV_FILE):
            with open(PROF_CSV_FILE, "rb") as file:
                st.download_button(
                    label="\U0001F4E5 Download Results CSV",
                    data=file,
                    file_name="prof_quiz_results.csv",
                    mime="text/csv"
                )
        else:
            st.warning("No results available yet.")

elif choice == "Professor Monitoring Panel":
    if not st.session_state.prof_verified:
        st.warning("Professor access only. Please login via 'Professor Panel' to verify.")
    else:
        st.header("\U0001F4E1 Live Student Monitoring")
        st.info("Students currently taking the quiz will appear here.")
        live_stream_ids = get_live_students()
        if not live_stream_ids:
            st.write("No active students currently taking the quiz.")
        else:
            for student_id in live_stream_ids:
                st.subheader(f"Live Feed from: {student_id}")
                st.warning("Note: Real-time video streaming from remote users is not supported on Streamlit Community Cloud.")
                st.write(f"\U0001F464 {student_id} is currently taking the quiz.")
