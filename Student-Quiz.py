# streamlit_quiz_app.py

import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import time
import os
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase

# -- Configuration --
st.set_page_config(page_title="Secure Quiz App", layout="wide")

# -- Database setup --
def create_users_table():
    conn = sqlite3.connect("quiz_app.db")
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        email TEXT,
        role TEXT,
        section TEXT,
        password_change_count INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

create_users_table()

# -- Helper Functions --
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    conn = sqlite3.connect("quiz_app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hash_password(password)))
    result = cur.fetchone()
    conn.close()
    return result

def update_password(username, new_password):
    conn = sqlite3.connect("quiz_app.db")
    cur = conn.cursor()
    cur.execute("SELECT password_change_count FROM users WHERE username=?", (username,))
    count = cur.fetchone()[0]
    if count < 2:
        cur.execute("UPDATE users SET password=?, password_change_count=password_change_count+1 WHERE username=?",
                    (hash_password(new_password), username))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def add_user(username, password, email, role, section):
    conn = sqlite3.connect("quiz_app.db")
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, 0)",
                    (username, hash_password(password), email, role, section))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def save_quiz_result(username, section, score):
    filename = f"results_{section}.csv"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df = pd.DataFrame([[username, score, timestamp]], columns=["Username", "Score", "Timestamp"])
    if os.path.exists(filename):
        df.to_csv(filename, mode='a', index=False, header=False)
    else:
        df.to_csv(filename, index=False)

# Webcam transformer for visual indication
class SimpleCam(VideoTransformerBase):
    def transform(self, frame):
        return frame

# -- UI Functions --
def registration():
    st.subheader("Register")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    email = st.text_input("Email")
    section = st.text_input("Section")
    role = st.selectbox("Role", ["student", "professor"])
    if st.button("Register"):
        if add_user(username, password, email, role, section):
            st.success("Registered successfully!")
        else:
            st.error("Username already exists!")

def login():
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate_user(username, password)
        if user:
            st.session_state['user'] = user
            st.success(f"Welcome {user[0]} ({user[3]})")
        else:
            st.error("Invalid credentials")

def quiz():
    user = st.session_state.get('user')
    if not user:
        st.warning("Please login first")
        return
    if 'quiz_attempts' not in st.session_state:
        st.session_state['quiz_attempts'] = {}
    if st.session_state['quiz_attempts'].get(user[0], 0) >= 2:
        st.warning("Maximum attempts reached!")
        return

    st.subheader("Quiz Section")
    webrtc_streamer(key="quiz_cam", video_processor_factory=SimpleCam)

    with st.form("quiz_form"):
        q1 = st.radio("Q1: Capital of India?", ["Delhi", "Mumbai", "Chennai"])
        q2 = st.radio("Q2: 5 + 3 = ?", ["5", "8", "10"])
        submit_btn = st.form_submit_button("Submit Quiz")

        if submit_btn:
            score = 0
            score += 1 if q1 == "Delhi" else 0
            score += 1 if q2 == "8" else 0
            st.session_state['quiz_attempts'][user[0]] = st.session_state['quiz_attempts'].get(user[0], 0) + 1
            save_quiz_result(user[0], user[4], score)
            st.success(f"Your score is {score}/2")

            # End quiz timer manually
            st.session_state['quiz_end'] = True

def countdown_timer():
    if 'start_time' not in st.session_state:
        st.session_state['start_time'] = time.time()
    elapsed = time.time() - st.session_state['start_time']
    remaining = 25 * 60 - elapsed
    if remaining > 0:
        mins, secs = divmod(int(remaining), 60)
        st.info(f"Time Left: {mins:02}:{secs:02}")
        st.experimental_rerun()
    else:
        st.warning("Time is up! Quiz auto-submitted.")
        st.session_state['quiz_end'] = True

def change_password():
    st.subheader("Change Password")
    username = st.text_input("Username")
    new_password = st.text_input("New Password", type="password")
    if st.button("Change"):
        if update_password(username, new_password):
            st.success("Password updated")
        else:
            st.error("Password change limit reached or user not found")

def professor_panel():
    st.subheader("Professor Panel - View Results")
    uploaded_sections = [f for f in os.listdir() if f.startswith("results_") and f.endswith(".csv")]
    for file in uploaded_sections:
        df = pd.read_csv(file)
        st.write(file)
        st.dataframe(df)

def main():
    st.title("📘 Secure Student Quiz Portal")
    menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Register":
        registration()
    elif choice == "Login":
        login()
    elif choice == "Take Quiz":
        if st.session_state.get('user'):
            countdown_timer()
            if not st.session_state.get('quiz_end'):
                quiz()
        else:
            st.warning("Login required")
    elif choice == "Change Password":
        change_password()
    elif choice == "Professor Panel":
        professor_panel()

if __name__ == '__main__':
    main()
