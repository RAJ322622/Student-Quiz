import streamlit as st
import pandas as pd
import os
import json
import hashlib
from datetime import datetime, timedelta
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
from gtts import gTTS
from moviepy.editor import *
import uuid
import smtplib
from email.message import EmailMessage

# Constants
QUIZ_DURATION = 25  # in minutes
MAX_ATTEMPTS = 2
MAX_PASSWORD_CHANGES = 2
USER_DATA_FILE = "user_data.csv"
PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_STUDENTS_FILE = "active_students.json"
QUIZ_QUESTIONS = [
    {
        "question": "What is the capital of France?",
        "options": ["London", "Berlin", "Paris", "Madrid"],
        "answer": "Paris"
    },
    {
        "question": "Which planet is known as the Red Planet?",
        "options": ["Earth", "Mars", "Jupiter", "Saturn"],
        "answer": "Mars"
    },
    {
        "question": "Who wrote '1984'?",
        "options": ["George Orwell", "Mark Twain", "J.K. Rowling", "Ernest Hemingway"],
        "answer": "George Orwell"
    }
]

# Ensure user data CSV exists
if not os.path.exists(USER_DATA_FILE):
    pd.DataFrame(columns=["username", "password", "attempts", "password_changes", "usn", "section", "email"]).to_csv(USER_DATA_FILE, index=False)

# Load or initialize active students JSON
if not os.path.exists(ACTIVE_STUDENTS_FILE):
    with open(ACTIVE_STUDENTS_FILE, 'w') as f:
        json.dump([], f)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def load_users():
    return pd.read_csv(USER_DATA_FILE)

def save_users(df):
    df.to_csv(USER_DATA_FILE, index=False)

def add_active_student(username):
    with open(ACTIVE_STUDENTS_FILE, 'r+') as f:
        data = json.load(f)
        if username not in data:
            data.append(username)
            f.seek(0)
            json.dump(data, f)
            f.truncate()

def remove_active_student(username):
    with open(ACTIVE_STUDENTS_FILE, 'r+') as f:
        data = json.load(f)
        if username in data:
            data.remove(username)
            f.seek(0)
            json.dump(data, f)
            f.truncate()

def send_email(to_email, subject, body):
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = "your-email@example.com"
        msg['To'] = to_email

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login("your-email@example.com", "your-password")
            server.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

def quiz_interface():
    st.title("Secure Student Quiz")

    if not st.session_state.get("quiz_started"):
        st.text_input("Enter your USN", key="usn")
        st.text_input("Enter your Section", key="section")
        if st.button("Start Quiz"):
            st.session_state.quiz_started = True
            st.session_state.quiz_start_time = datetime.now()
            st.session_state.quiz_submitted = False
            st.session_state.camera_active = True
            add_active_student(st.session_state.username)

    if st.session_state.get("quiz_started") and not st.session_state.get("quiz_submitted"):
        if st.session_state.get("camera_active"):
            webrtc_streamer(key="quiz")

        remaining = QUIZ_DURATION - (datetime.now() - st.session_state.quiz_start_time).seconds // 60
        st.info(f"Time Remaining: {remaining} minutes")

        answers = {}
        for idx, question in enumerate(QUIZ_QUESTIONS):
            st.subheader(question['question'])
            ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
            answers[idx] = ans

        if st.button("Submit Quiz") or remaining <= 0:
            score = sum(1 for idx, question in enumerate(QUIZ_QUESTIONS) if answers[idx] == question['answer'])
            st.success(f"Quiz Submitted! Your Score: {score}/{len(QUIZ_QUESTIONS)}")
            st.session_state.quiz_submitted = True
            st.session_state.camera_active = False

            # CSV logging
            new_row = {
                'username': st.session_state.username,
                'usn': st.session_state.usn,
                'section': st.session_state.section,
                'score': score,
                'timestamp': datetime.now()
            }
            for file in [PROF_CSV_FILE, STUDENT_CSV_FILE, f"section_{st.session_state.section}_results.csv"]:
                df = pd.read_csv(file) if os.path.exists(file) else pd.DataFrame()
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(file, index=False)

            remove_active_student(st.session_state.username)
            st.session_state.pop("quiz_start_time", None)

            # Optional email result
            df_users = load_users()
            user_row = df_users[df_users['username'] == st.session_state.username]
            if not user_row.empty:
                send_email(user_row.iloc[0]['email'], "Quiz Result", f"Your quiz score is {score}/{len(QUIZ_QUESTIONS)}")

def login():
    st.title("Student Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    df = load_users()
    user = df[df['username'] == username]
    if st.button("Login"):
        if not user.empty and verify_password(password, user.iloc[0]['password']):
            if user.iloc[0]['attempts'] >= MAX_ATTEMPTS:
                st.error("Max attempts reached.")
            else:
                df.loc[df['username'] == username, 'attempts'] += 1
                save_users(df)
                st.session_state.username = username
                st.session_state.usn = user.iloc[0]['usn']
                st.session_state.section = user.iloc[0]['section']
                quiz_interface()
        else:
            st.error("Invalid credentials")

def register():
    st.title("Register")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    email = st.text_input("Email")
    usn = st.text_input("USN")
    section = st.text_input("Section")
    if st.button("Register"):
        df = load_users()
        if username in df['username'].values:
            st.warning("User exists")
        else:
            hashed_pw = hash_password(password)
            new_user = pd.DataFrame([[username, hashed_pw, 0, 0, usn, section, email]], columns=df.columns)
            df = pd.concat([df, new_user], ignore_index=True)
            save_users(df)
            st.success("Registered")

def change_password():
    st.title("Change Password")
    username = st.text_input("Username")
    old = st.text_input("Old Password", type="password")
    new = st.text_input("New Password", type="password")
    df = load_users()
    user = df[df['username'] == username]
    if st.button("Update"):
        if not user.empty and verify_password(old, user.iloc[0]['password']):
            if user.iloc[0]['password_changes'] >= MAX_PASSWORD_CHANGES:
                st.error("Password change limit reached")
            else:
                df.loc[df['username'] == username, 'password'] = hash_password(new)
                df.loc[df['username'] == username, 'password_changes'] += 1
                save_users(df)
                st.success("Password updated")
        else:
            st.error("Invalid credentials")

def prof_panel():
    st.title("Professor Panel")
    key = st.text_input("Enter Professor Key")
    if st.button("Verify"):
        if key == "prof123":
            st.session_state.prof_verified = True
    if st.session_state.get("prof_verified"):
        st.subheader("Live Students")
        with open(ACTIVE_STUDENTS_FILE, 'r') as f:
            live = json.load(f)
        st.write(live)

        for label, file in {
            "All Results": PROF_CSV_FILE,
            "Student Results": STUDENT_CSV_FILE
        }.items():
            if os.path.exists(file):
                with open(file, "rb") as f:
                    st.download_button(f"Download {label}", f, file, mime="text/csv")

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Login", "Register", "Change Password", "Professor Panel"])

if page == "Login":
    login()
elif page == "Register":
    register()
elif page == "Change Password":
    change_password()
elif page == "Professor Panel":
    prof_panel()
