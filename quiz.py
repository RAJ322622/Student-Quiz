import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""

if "camera_active" not in st.session_state:
    st.session_state.camera_active = False

if "prof_verified" not in st.session_state:
    st.session_state.prof_verified = False

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

# Questions
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

# UI Starts
st.title("🎓 Secure Quiz App with Webcam 🎥")

menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel"]
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
        conn = get_db_connection()
        cur = conn.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (username,))
        row = cur.fetchone()

        if row and row[0] >= 2:
            st.error("You have already taken the quiz 2 times.")
        else:
            score = 0
            start_time = time.time()
            answers = {}

            # Activate camera at quiz start
            if not st.session_state.camera_active:
                st.session_state.camera_active = True
                st.subheader("📷 Webcam Monitoring (ON During Quiz Only)")
                webrtc_streamer(
                    key="quiz_camera",
                    mode=WebRtcMode.SENDRECV,
                    media_stream_constraints={"video": True, "audio": False}
                )

            for idx, question in enumerate(QUESTIONS):
                st.markdown(f"**Q{idx+1}:** {question['question']}")
                ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                answers[question['question']] = ans

            if st.button("Submit Quiz"):
                for q in QUESTIONS:
                    if answers.get(q["question"]) == q["answer"]:
                        score += 1
                time_taken = round(time.time() - start_time, 2)
                df = pd.DataFrame([[username, hash_password(username), score, time_taken, datetime.now()]],
                                  columns=["Username", "Hashed_Password", "Score", "Time_Taken", "Timestamp"])
                try:
                    old_df_prof = pd.read_csv(PROF_CSV_FILE)
                    df = pd.concat([old_df_prof, df], ignore_index=True)
                except FileNotFoundError:
                    pass
                df.to_csv(PROF_CSV_FILE, index=False)
                df[["Username", "Score", "Time_Taken", "Timestamp"]].to_csv(STUDENT_CSV_FILE, mode='a', index=False, header=not os.path.exists(STUDENT_CSV_FILE))
                st.success(f"Quiz submitted! Your score: {score}")

                # Update attempt count
                if row:
                    conn.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                else:
                    conn.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, 1)", (username,))
                conn.commit()
                conn.close()

                # Turn off camera after quiz
                st.session_state.camera_active = False

elif choice == "Change Password":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm Password", type="password")

        if st.button("Update Password"):
            if new_pass != confirm_pass:
                st.error("Passwords do not match!")
            else:
                conn = get_db_connection()
                cur = conn.execute("SELECT change_count FROM password_changes WHERE username = ?", (username,))
                result = cur.fetchone()
                if result and result[0] >= 2:
                    st.error("You have already changed your password 2 times.")
                else:
                    conn.execute("UPDATE users SET password = ? WHERE username = ?", (hash_password(new_pass), username))
                    if result:
                        conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?", (username,))
                    else:
                        conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)", (username,))
                    conn.commit()
                    st.success("Password updated successfully.")
                conn.close()

elif choice == "Professor Panel":
    st.subheader("🧑‍🏫 Professor Access Panel")

    if not st.session_state.prof_verified:
        prof_user = st.text_input("Professor Username")
        prof_pass = st.text_input("Professor Password", type="password")
        if st.button("Verify Professor"):
            if prof_user.strip().lower() == "raj kumar" and prof_pass.strip().lower() == "raj kumar":
                st.session_state.prof_verified = True
                st.success("Professor verified! You can now download results.")
            else:
                st.error("Access denied. Invalid professor credentials.")
    else:
        st.success("Welcome Professor Raj Kumar!")
        if os.path.exists(PROF_CSV_FILE):
            with open(PROF_CSV_FILE, "rb") as file:
                st.download_button(
                    label="📥 Download Results CSV",
                    data=file,
                    file_name="prof_quiz_results.csv",
                    mime="text/csv"
                )
        else:
            st.warning("No results available yet.")
