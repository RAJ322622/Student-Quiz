
# Streamlit Secure Quiz Application with Full Features in One File
import streamlit as st
import pandas as pd
import datetime
import time
import cv2
from gtts import gTTS
import os
import uuid
import base64
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "login"
if "username" not in st.session_state:
    st.session_state.username = ""
if "password_change_count" not in st.session_state:
    st.session_state.password_change_count = {}
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "usn" not in st.session_state:
    st.session_state.usn = ""
if "section" not in st.session_state:
    st.session_state.section = ""

# Constants
QUIZ_TIME_LIMIT = 25 * 60  # 25 minutes
QUIZ_ATTEMPT_LIMIT = 2
QUESTIONS = {
    "What is the capital of France?": "Paris",
    "2 + 2 = ?": "4",
    "What color is the sky?": "Blue"
}

# Load or initialize user and attempt data
def load_users():
    if os.path.exists("users.csv"):
        return pd.read_csv("users.csv")
    return pd.DataFrame(columns=["username", "password", "email", "password_changes", "attempts"])

def save_users(df):
    df.to_csv("users.csv", index=False)

def send_email(to_email, subject, content):
    try:
        from_email = st.secrets["email"]["from_email"]
        api_key = st.secrets["email"]["sendgrid_api_key"]
        message = Mail(from_email=from_email, to_emails=to_email, subject=subject, html_content=content)
        sg = SendGridAPIClient(api_key)
        sg.send(message)
        return True
    except Exception as e:
        print("Email error:", e)
        return False

# Webcam capture simulation
def capture_image():
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    if ret:
        filename = f"{uuid.uuid4().hex}.jpg"
        cv2.imwrite(filename, frame)
        cap.release()
        return filename
    cap.release()
    return None

# Quiz timer
def start_quiz_timer():
    if st.session_state.start_time is None:
        st.session_state.start_time = time.time()

    elapsed = time.time() - st.session_state.start_time
    remaining = max(0, QUIZ_TIME_LIMIT - elapsed)

    mins, secs = divmod(int(remaining), 60)
    st.warning(f"Time Remaining: {mins:02d}:{secs:02d}")

    if remaining <= 0:
        st.success("Time's up! Auto-submitting quiz.")
        return False
    return True

# Registration
def register():
    st.title("Register")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    email = st.text_input("Email")
    if st.button("Register"):
        df = load_users()
        if username in df["username"].values:
            st.error("Username already exists.")
        else:
            df = df.append({"username": username, "password": password, "email": email,
                            "password_changes": 0, "attempts": 0}, ignore_index=True)
            save_users(df)
            send_email(email, "Registration Successful", f"Welcome, {username}! You are registered.")
            st.success("Registered successfully!")
            st.session_state.page = "login"

# Login
def login():
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        df = load_users()
        user = df[df["username"] == username]
        if not user.empty and user.iloc[0]["password"] == password:
            st.session_state.username = username
            st.session_state.usn = st.text_input("Enter your USN:")
            st.session_state.section = st.text_input("Enter your Section:")
            st.session_state.page = "quiz"
        else:
            st.error("Invalid login.")

# Password Reset
def reset_password():
    st.title("Reset Password")
    username = st.text_input("Username")
    new_pass = st.text_input("New Password", type="password")
    if st.button("Reset"):
        df = load_users()
        user_idx = df[df["username"] == username].index
        if not user_idx.empty:
            i = user_idx[0]
            if df.at[i, "password_changes"] < 2:
                df.at[i, "password"] = new_pass
                df.at[i, "password_changes"] += 1
                save_users(df)
                send_email(df.at[i, "email"], "Password Reset", f"Hi {username}, your password was reset.")
                st.success("Password reset.")
            else:
                st.error("Password change limit reached.")
        else:
            st.error("User not found.")

# Quiz Page
def quiz():
    st.title("Take Quiz")
    df = load_users()
    user = df[df["username"] == st.session_state.username]
    if user.empty or user.iloc[0]["attempts"] >= QUIZ_ATTEMPT_LIMIT:
        st.warning("Attempt limit reached.")
        return

    capture_image()  # Simulate webcam snapshot

    proceed = start_quiz_timer()
    if not proceed:
        submit_quiz({})
        return

    answers = {}
    for q in QUESTIONS:
        answers[q] = st.text_input(q)

    if st.button("Submit"):
        submit_quiz(answers)

def submit_quiz(answers):
    correct = sum(1 for q, a in answers.items() if a.strip().lower() == QUESTIONS[q].lower())
    total = len(QUESTIONS)
    df = load_users()
    idx = df[df["username"] == st.session_state.username].index[0]
    df.at[idx, "attempts"] += 1
    save_users(df)

    results_df = pd.DataFrame([[st.session_state.username, st.session_state.usn,
                                 correct, total, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")]],
                               columns=["Username", "USN", "Score", "Total", "Time"])
    filename = f"results_{st.session_state.section}.csv"
    if os.path.exists(filename):
        old = pd.read_csv(filename)
        results_df = pd.concat([old, results_df], ignore_index=True)
    results_df.to_csv(filename, index=False)

    st.success(f"Score: {correct}/{total}")
    send_email(df.at[idx, "email"], "Quiz Result",
               f"Hello {st.session_state.username}, your score: {correct}/{total}")

    st.session_state.page = "login"
    st.session_state.quiz_started = False
    st.session_state.start_time = None

# Professor Panel
def professor_panel():
    st.title("Professor Panel")
    section = st.text_input("Enter section to download results")
    if st.button("Download Results"):
        filename = f"results_{section}.csv"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV</a>'
                st.markdown(href, unsafe_allow_html=True)
        else:
            st.error("No results found.")

# Main App Router
def main():
    pages = {
        "login": login,
        "register": register,
        "reset": reset_password,
        "quiz": quiz,
        "professor": professor_panel
    }

    menu = ["Login", "Register", "Reset Password", "Professor Panel"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Login":
        st.session_state.page = "login"
    elif choice == "Register":
        st.session_state.page = "register"
    elif choice == "Reset Password":
        st.session_state.page = "reset"
    elif choice == "Professor Panel":
        st.session_state.page = "professor"

    pages[st.session_state.page]()

main()
