import streamlit as st
import sqlite3
import pandas as pd
import random
import cv2
import os
import smtplib
import string
import time
from email.message import EmailMessage
from datetime import datetime, timedelta

# Initialize database
conn = sqlite3.connect("quiz_app.db", check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    email TEXT,
    section TEXT,
    attempts INTEGER DEFAULT 0,
    password_changes INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS otp_sessions (
    username TEXT,
    otp TEXT,
    purpose TEXT
)''')

conn.commit()

# Sample quiz
quiz = {
    "What is the capital of France?": "Paris",
    "2 + 2 = ?": "4",
    "Color of the sky on a clear day?": "Blue"
}

# Email credentials
EMAIL_ADDRESS = "rajkumar.k0322@gmail.com"
EMAIL_PASSWORD = "kcxflzrqxntsxlng"  # App password, not your regular Gmail password

def send_email(recipient, subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = recipient
    msg.set_content(body)

    # ✅ Correct SMTP host and port
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


    

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def capture_image(username):
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    if ret:
        filepath = f"{username}_snapshot.jpg"
        cv2.imwrite(filepath, frame)
    cap.release()

def store_result(username, section, score):
    filename = f"{section}_results.csv"
    new_data = pd.DataFrame([[username, score]], columns=["Username", "Score"])
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        df = df[df['Username'] != username]  # remove old
        df = pd.concat([df, new_data], ignore_index=True)
    else:
        df = new_data
    df.to_csv(filename, index=False)

# UI
st.title("🎓 Secure Quiz App with Webcam & Email")

menu = st.sidebar.selectbox("Menu", ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"])

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "section" not in st.session_state:
    st.session_state.section = ""
if "quiz_start_time" not in st.session_state:
    st.session_state.quiz_start_time = None
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False

# Register
if menu == "Register":
    st.subheader("Register")
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    section = st.text_input("Section")

    if st.button("Send OTP"):
        otp = generate_otp()
        cursor.execute("DELETE FROM otp_sessions WHERE username=? AND purpose='register'", (username,))
        cursor.execute("INSERT INTO otp_sessions (username, otp, purpose) VALUES (?, ?, ?)", (username, otp, 'register'))
        conn.commit()
        send_email(email, "OTP for Registration", f"Your OTP is: {otp}")
        st.success("OTP sent to your email.")

    entered_otp = st.text_input("Enter OTP", type="password")
    if st.button("Verify & Register"):
        cursor.execute("SELECT otp FROM otp_sessions WHERE username=? AND purpose='register'", (username,))
        record = cursor.fetchone()
        if record and entered_otp == record[0]:
            cursor.execute("INSERT INTO users (username, password, email, section) VALUES (?, ?, ?, ?)", (username, password, email, section))
            conn.commit()
            st.success("Registration successful!")
        else:
            st.error("Invalid OTP.")

# Login
elif menu == "Login":
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Send OTP"):
        cursor.execute("SELECT email FROM users WHERE username=? AND password=?", (username, password))
        user = cursor.fetchone()
        if user:
            otp = generate_otp()
            cursor.execute("DELETE FROM otp_sessions WHERE username=? AND purpose='login'", (username,))
            cursor.execute("INSERT INTO otp_sessions (username, otp, purpose) VALUES (?, ?, ?)", (username, otp, 'login'))
            conn.commit()
            send_email(user[0], "OTP for Login", f"Your OTP is: {otp}")
            st.success("OTP sent to your email.")
        else:
            st.error("Invalid username or password")

    entered_otp = st.text_input("Enter OTP to Login", type="password")
    if st.button("Verify & Login"):
        cursor.execute("SELECT otp FROM otp_sessions WHERE username=? AND purpose='login'", (username,))
        record = cursor.fetchone()
        if record and entered_otp == record[0]:
            st.success("Login successful!")
            st.session_state.authenticated = True
            st.session_state.username = username
            cursor.execute("SELECT section FROM users WHERE username=?", (username,))
            st.session_state.section = cursor.fetchone()[0]
        else:
            st.error("Invalid OTP.")

# Forgot Password
elif menu == "Change Password":
    st.subheader("Forgot Password")
    username = st.text_input("Username")
    if st.button("Send OTP to Reset Password"):
        cursor.execute("SELECT email FROM users WHERE username=?", (username,))
        result = cursor.fetchone()
        if result:
            otp = generate_otp()
            cursor.execute("DELETE FROM otp_sessions WHERE username=? AND purpose='reset'", (username,))
            cursor.execute("INSERT INTO otp_sessions (username, otp, purpose) VALUES (?, ?, ?)", (username, otp, 'reset'))
            conn.commit()
            send_email(result[0], "OTP to Reset Password", f"Your OTP is: {otp}")
            st.success("OTP sent to your email.")
        else:
            st.error("User not found.")

    entered_otp = st.text_input("Enter OTP to Reset", type="password")
    new_pass = st.text_input("New Password", type="password")
    if st.button("Reset Password"):
        cursor.execute("SELECT otp FROM otp_sessions WHERE username=? AND purpose='reset'", (username,))
        record = cursor.fetchone()
        if record and entered_otp == record[0]:
            cursor.execute("SELECT password_changes FROM users WHERE username=?", (username,))
            count = cursor.fetchone()[0]
            if count < 2:
                cursor.execute("UPDATE users SET password=?, password_changes=password_changes+1 WHERE username=?", (new_pass, username))
                conn.commit()
                st.success("Password updated!")
            else:
                st.warning("You’ve reached the maximum number of password changes.")
        else:
            st.error("Invalid OTP.")

# Take Quiz
elif menu == "Take Quiz" and st.session_state.authenticated:
    st.subheader("Take Quiz")

    cursor.execute("SELECT attempts FROM users WHERE username=?", (st.session_state.username,))
    attempts = cursor.fetchone()[0]

    if attempts >= 2:
        st.warning("You've used all your attempts.")
    elif not st.session_state.quiz_submitted:
        if st.button("Start Quiz"):
            st.session_state.quiz_start_time = datetime.now()
            capture_image(st.session_state.username)
        if st.session_state.quiz_start_time:
            remaining = 1500 - (datetime.now() - st.session_state.quiz_start_time).seconds
            if remaining <= 0:
                st.warning("Time up! Submitting...")
                st.session_state.quiz_submitted = True
            else:
                st.info(f"⏳ Time left: {remaining//60}:{remaining%60:02}")
                answers = {}
                for q in quiz:
                    answers[q] = st.text_input(q)
                if st.button("Submit"):
                    score = sum(1 for q in quiz if answers.get(q, "").strip().lower() == quiz[q].lower())
                    store_result(st.session_state.username, st.session_state.section, score)
                    cursor.execute("UPDATE users SET attempts = attempts + 1 WHERE username=?", (st.session_state.username,))
                    conn.commit()
                    st.success(f"Quiz submitted! Your score: {score}")
                    cursor.execute("SELECT email FROM users WHERE username=?", (st.session_state.username,))
                    email = cursor.fetchone()[0]
                    send_email(email, "Your Quiz Score", f"You scored: {score}")
                    st.session_state.quiz_submitted = True

# Professor Panel
elif menu == "Professor Panel":
    st.subheader("View Results")
    section = st.text_input("Enter section to view results:")
    if st.button("Load Section Results"):
        filename = f"{section}_results.csv"
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            st.dataframe(df)
        else:
            st.warning("No results found for this section.")

# Professor Monitoring Panel
elif menu == "Professor Monitoring Panel":
    st.subheader("Monitor Students")
    files = [f for f in os.listdir() if f.endswith("_snapshot.jpg")]
    for img in files:
        st.image(img, caption=img)

# View Recorded Video
elif menu == "View Recorded Video":
    st.subheader("Not implemented: Only snapshots supported")

