import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
from datetime import datetime
import os

# Setup
CSV_FILE = "quiz_results.csv"
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

# DB setup
def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)''')
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
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

# Questions
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

# UI
st.title("🎓 Quiz App (Cloud Compatible)")

menu = ["Register", "Login", "Take Quiz", "View Results"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Register"):
        register_user(username, password)

elif choice == "Login":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.success("Login successful!")
        else:
            st.error("Invalid credentials!")

elif choice == "Take Quiz":
    if not st.session_state["logged_in"]:
        st.warning("Please login first!")
    else:
        score = 0
        start_time = time.time()
        answers = {}
        st.info("📷 Camera monitoring is not supported on Streamlit Cloud.")

        for idx, q in enumerate(QUESTIONS):
            st.markdown(f"**Q{idx+1}:** {q['question']}")
            ans = st.radio("Select your answer:", q['options'], key=f"q{idx}")
            answers[q['question']] = ans

        if st.button("Submit Quiz"):
            for q in QUESTIONS:
                if answers.get(q["question"]) == q["answer"]:
                    score += 1
            time_taken = round(time.time() - start_time, 2)

            df = pd.DataFrame([[st.session_state["username"], score, time_taken, datetime.now()]],
                              columns=["Username", "Score", "Time_Taken", "Timestamp"])
            try:
                old_df = pd.read_csv(CSV_FILE)
                df = pd.concat([old_df, df], ignore_index=True)
            except FileNotFoundError:
                pass
            df.to_csv(CSV_FILE, index=False)
            st.success(f"Quiz submitted! Your score: {score}")

elif choice == "View Results":
    try:
        df = pd.read_csv(CSV_FILE)
        st.dataframe(df)
    except FileNotFoundError:
        st.warning("No quiz results yet.")
