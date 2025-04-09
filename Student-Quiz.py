import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from streamlit_autorefresh import st_autorefresh

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"

# Session state defaults
for key in ["logged_in", "username", "camera_active", "prof_verified", "quiz_submitted", "student_section"]:
    if key not in st.session_state:
        st.session_state[key] = False if key != "username" and key != "student_section" else ""

if "start_time" not in st.session_state:
    st.session_state.start_time = 0

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
        section = st.text_input("Enter your Section (e.g., A, B, C):")
        if section:
            st.session_state.student_section = section.upper()

        if not st.session_state.student_section:
            st.warning("Please enter your section before proceeding.")
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (username,))
            record = cur.fetchone()
            attempt_count = record[0] if record else 0

            if attempt_count >= 2:
                st.error("You have already taken the quiz 2 times. No more attempts allowed.")
            else:
                score = 0
                if not st.session_state.quiz_submitted and not st.session_state.camera_active:
                    add_active_student(username)
                    st.session_state.camera_active = True
                    st.session_state.start_time = time.time()

                if not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_streamer(
                        key="quiz_camera_fixed_key",  # Use a constant key
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

                answers = {}
                for idx, question in enumerate(QUESTIONS):
                    st.markdown(f"**Q{idx+1}:** {question['question']}")
                    ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                    answers[question['question']] = ans

                if st.button("Submit Quiz") and not st.session_state.quiz_submitted:
                    if None in answers.values():
                        st.error("Please answer all questions before submitting the quiz.")
                    else:
                        for q in QUESTIONS:
                            if answers.get(q["question"]) == q["answer"]:
                                score += 1
                        time_taken = round(time.time() - st.session_state.start_time, 2)

                        new_row = pd.DataFrame([[username, hash_password(username), score, time_taken, datetime.now(), st.session_state.student_section]],
                                               columns=["Username", "Hashed_Password", "Score", "Time_Taken", "Timestamp", "Section"])

                        try:
                            old_df_prof = pd.read_csv(PROF_CSV_FILE)
                            full_df = pd.concat([old_df_prof, new_row], ignore_index=True)
                        except FileNotFoundError:
                            full_df = new_row
                        full_df.to_csv(PROF_CSV_FILE, index=False)

                        new_row[["Username", "Score", "Time_Taken", "Timestamp"]].to_csv(
                            STUDENT_CSV_FILE, mode='a', index=False, header=not os.path.exists(STUDENT_CSV_FILE)
                        )

                        section_file = f"section_{st.session_state.student_section}.csv"
                        try:
                            old_section_df = pd.read_csv(section_file)
                            section_df = pd.concat([old_section_df, new_row], ignore_index=True)
                        except FileNotFoundError:
                            section_df = new_row
                        section_df.to_csv(section_file, index=False)

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

elif choice == "Change Password":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        old_pass = st.text_input("Old Password", type="password")
        new_pass = st.text_input("New Password", type="password")

        if st.button("Change Password"):
            if not authenticate_user(username, old_pass):
                st.error("Old password is incorrect!")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT change_count FROM password_changes WHERE username = ?", (username,))
                record = cursor.fetchone()

                if record and record[0] >= 2:
                    st.error("Password can only be changed twice.")
                else:
                    conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                 (hash_password(new_pass), username))

                    if record:
                        conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                     (username,))
                    else:
                        conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                     (username,))
                    conn.commit()
                    st.success("Password updated successfully.")
                conn.close()

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
        st_autorefresh(interval=10 * 1000, key="monitor_refresh")
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
