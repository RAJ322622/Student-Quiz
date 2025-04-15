import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase
from streamlit_autorefresh import st_autorefresh
import av
import smtplib
from email.message import EmailMessage
import random

def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = "rajkumar.k0322@gmail.com"
        msg['To'] = to_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")  # App Password
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
os.makedirs(RECORDING_DIR, exist_ok=True)

# Session state defaults
for key in ["logged_in", "username", "camera_active", "prof_verified", "quiz_submitted", "usn", "section"]:
    if key not in st.session_state:
        st.session_state[key] = False if key not in ["username", "usn", "section"] else ""

def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    role TEXT DEFAULT 'student')''')

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if "email" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()

    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                    username TEXT PRIMARY KEY,
                    change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                    username TEXT PRIMARY KEY,
                    attempt_count INTEGER DEFAULT 0)''')
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role, email):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                     (username, hash_password(password), role, email))
        conn.commit()
        st.success("Registration successful! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    finally:
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

# Updated VideoProcessor class with proper recording handling
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.frames = []
        self.recording_started = False
        
    def recv(self, frame):
        if not self.recording_started:
            self.recording_started = True
            st.session_state.recording_start_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            
        self.frames.append(frame)
        return frame
    
    def on_ended(self):
        self.save_recording()
        
    def save_recording(self):
        if self.frames and 'username' in st.session_state:
            filename = f"{st.session_state.username}_{st.session_state.recording_start_time}.mp4"
            filepath = os.path.join(RECORDING_DIR, filename)
            
            container = av.open(filepath, mode='w')
            stream = container.add_stream('h264', rate=30)
            stream.width = self.frames[0].width
            stream.height = self.frames[0].height
            
            for frame in self.frames:
                img = frame.to_ndarray(format="bgr24")
                av_frame = av.VideoFrame.from_ndarray(img, format="bgr24")
                for packet in stream.encode(av_frame):
                    container.mux(packet)
                    
            for packet in stream.encode():
                container.mux(packet)
                
            container.close()
            st.session_state.last_recording = filename

QUESTIONS = [
    {
        "question": "Which keyword is used to define a constant in C?",
        "options": ["const", "#define", "static", "let"],
        "answer": "const"
    },
    {
        "question": "What is the output of `print(3 * 'a' in Python)?",
        "options": ["aaa", "a a a", "Error", "True"],
        "answer": "aaa"
    },
    {
        "question": "Which data structure uses FIFO (First-In-First-Out)?",
        "options": ["Stack", "Queue", "Array", "Linked List"],
        "answer": "Queue"
    },
    {
        "question": "What does `sizeof(int)` return in a 32-bit system?",
        "options": ["2", "4", "8", "Compiler-dependent"],
        "answer": "4"
    },
    {
        "question": "Which Python function converts a string to lowercase?",
        "options": ["str.lower()", "string.lower()", "toLower()", "lowercase()"],
        "answer": "str.lower()"
    },
    {
        "question": "What is the time complexity of binary search?",
        "options": ["O(n)", "O(log n)", "O(n²)", "O(1)"],
        "answer": "O(log n)"
    },
    {
        "question": "Which operator is used for pointer dereferencing in C?",
        "options": ["&", "*", "->", "::"],
        "answer": "*"
    },
    {
        "question": "What does `'hello'.replace('l', 'x')` return in Python?",
        "options": ["hexxo", "hexlo", "helxo", "Error"],
        "answer": "hexxo"
    },
    {
        "question": "Which header file is needed for `printf()` in C?",
        "options": ["<stdio.h>", "<stdlib.h>", "<math.h>", "<string.h>"],
        "answer": "<stdio.h>"
    },
    {
        "question": "What is the default return type of a function in C if not specified?",
        "options": ["void", "int", "char", "float"],
        "answer": "int"
    }
]

# UI Starts
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["student"])

    if st.button("Send OTP"):
        if username and email and password:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(email, otp):
                st.session_state['reg_otp'] = otp
                st.session_state['reg_data'] = (username, hash_password(password), role, email)
                st.success("OTP sent to your email.")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if otp_entered == st.session_state.get('reg_otp'):
            username, password_hashed, role, email = st.session_state['reg_data']
            register_user(username, password_hashed, role, email)
        else:
            st.error("Incorrect OTP!")

elif choice == "Login":
    st.subheader("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login successful!")
        else:
            st.error("Invalid username or password.")

    st.markdown("### Forgot Password?")
    forgot_email = st.text_input("Enter registered email", key="forgot_email_input")
    if st.button("Send Reset OTP"):
        conn = get_db_connection()
        user = conn.execute("SELECT username FROM users WHERE email = ?", (forgot_email,)).fetchone()
        conn.close()

        if user:
            otp = str(random.randint(100000, 999999))
            st.session_state['reset_email'] = forgot_email
            st.session_state['reset_otp'] = otp
            st.session_state['reset_user'] = user[0]
            if send_email_otp(forgot_email, otp):
                st.success("OTP sent to your email.")
        else:
            st.error("Email not registered.")

    if 'reset_otp' in st.session_state and 'reset_email' in st.session_state:
        st.markdown("### Reset Your Password")
        entered_otp = st.text_input("Enter OTP to reset password", key="reset_otp_input")
        new_password = st.text_input("New Password", type="password", key="reset_new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="reset_confirm_password")

        if st.button("Reset Password"):
            if entered_otp == st.session_state.get('reset_otp'):
                if new_password == confirm_password:
                    conn = get_db_connection()
                    conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                 (hash_password(new_password), st.session_state['reset_user']))
                    conn.commit()
                    conn.close()
                    st.success("Password reset successfully! You can now log in.")
                    del st.session_state['reset_otp']
                    del st.session_state['reset_email']
                    del st.session_state['reset_user']
                else:
                    st.error("Passwords do not match.")
            else:
                st.error("Incorrect OTP.")


# In the Take Quiz section
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
                if "quiz_start_time" not in st.session_state:
                    st.session_state.quiz_start_time = time.time()
                    add_active_student(username)
                    st.session_state.camera_active = True

                time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                time_limit = 25 * 60
                time_left = time_limit - time_elapsed

                if time_left <= 0:
                    st.warning("⏰ Time is up! Auto-submitting your quiz.")
                    st.session_state.auto_submit = True
                else:
                    mins, secs = divmod(time_left, 60)
                    st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")

                answers = {}

                if st.session_state.camera_active and not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:green;'>🟢 Webcam is ON (Recording automatically started)</span>", unsafe_allow_html=True)
                    
                    # Initialize webrtc_streamer
                    webrtc_ctx = webrtc_streamer(
                        key="quiz_recording",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={
                            "video": {
                                "width": {"ideal": 640},
                                "height": {"ideal": 480},
                                "facingMode": "user"
                            },
                            "audio": False
                        },
                        video_processor_factory=VideoProcessor,
                        async_processing=True,
                        rtc_configuration={
                            "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
                        }
                    )
                    
                    # Handle camera state
                    if webrtc_ctx.state.playing:
                        st.session_state.camera_active = True
                    else:
                        st.warning("Camera is not active. Please allow camera permissions to continue.")
                        st.info("If the camera doesn't start automatically, please refresh the page and allow permissions when prompted.")

                # Rest of your quiz questions and submission logic...
                for idx, question in enumerate(QUESTIONS):
                    st.markdown(f"**Q{idx+1}:** {question['question']}")
                    ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                    answers[question['question']] = ans

                submit_btn = st.button("Submit Quiz")
                # ... rest of your submission logic


                submit_btn = st.button("Submit Quiz")
                auto_submit_triggered = st.session_state.get("auto_submit", False)

                if (submit_btn or auto_submit_triggered) and not st.session_state.quiz_submitted:
                    if None in answers.values():
                        st.error("Please answer all questions before submitting the quiz.")
                    else:
                        for q in QUESTIONS:
                            if answers.get(q["question"]) == q["answer"]:
                                score += 1
                        time_taken = round(time.time() - st.session_state.quiz_start_time, 2)

                        new_row = pd.DataFrame([[username, hash_password(username), st.session_state.usn, st.session_state.section, score, time_taken, datetime.now()]],
                                               columns=["Username", "Hashed_Password", "USN", "Section", "Score", "Time_Taken", "Timestamp"])

                        if os.path.exists(PROF_CSV_FILE):
                            prof_df = pd.read_csv(PROF_CSV_FILE)
                            prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                        else:
                            prof_df = new_row
                        prof_df.to_csv(PROF_CSV_FILE, index=False)

                        section_file = f"{st.session_state.section}_results.csv"
                        if os.path.exists(section_file):
                            sec_df = pd.read_csv(section_file)
                            sec_df = pd.concat([sec_df, new_row], ignore_index=True)
                        else:
                            sec_df = new_row
                        sec_df.to_csv(section_file, index=False)

                        if record:
                            cur.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                        else:
                            cur.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, ?)", (username, 1))
                        conn.commit()
                        conn.close()

                        email_conn = get_db_connection()
                        email_result = email_conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                        email_conn.close()
                        
                        if email_result:
                            student_email = email_result[0]
                            try:
                                msg = EmailMessage()
                                msg.set_content(f"Dear {username},\n\nYou scored {score}/{len(QUESTIONS)} in the Secure Quiz.\nTime Taken: {time_taken} seconds\n\nThank you!")
                                msg['Subject'] = "Quiz Submission Confirmation"
                                msg['From'] = "rajkumar.k0322@gmail.com"
                                msg['To'] = student_email

                                server = smtplib.SMTP('smtp.gmail.com', 587)
                                server.starttls()
                                server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
                                server.send_message(msg)
                                server.quit()
                            except Exception as e:
                                st.error(f"Result email failed: {e}")

                        st.success(f"Quiz submitted successfully! Your score is {score}/{len(QUESTIONS)}.")
                        st.session_state.quiz_submitted = True
                        st.session_state.camera_active = False
                        remove_active_student(username)

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
    
    # Professor registration and login tabs
    tab1, tab2 = st.tabs(["Professor Login", "Professor Registration"])
    
    with tab1:  # Login tab
        if not st.session_state.prof_verified:
            prof_id = st.text_input("Professor ID", key="prof_id_login")
            prof_pass = st.text_input("Professor Password", type="password", key="prof_pass_login")
            
            if st.button("Login as Professor"):
                conn = get_db_connection()
                cursor = conn.execute("SELECT password, role FROM users WHERE username = ?", (prof_id,))
                prof_data = cursor.fetchone()
                conn.close()
                
                if prof_data and prof_data[1] == "professor" and prof_data[0] == hash_password(prof_pass):
                    st.session_state.prof_verified = True
                    st.session_state.username = prof_id
                    st.success("Professor login successful!")
                else:
                    st.error("Invalid Professor ID or password")
        else:
            st.success(f"Welcome Professor {st.session_state.username}!")
            
            # Professor dashboard after login
            if os.path.exists(PROF_CSV_FILE):
                with open(PROF_CSV_FILE, "rb") as file:
                    st.download_button("\U0001F4E5 Download Results CSV", file, "prof_quiz_results.csv", mime="text/csv")
                
                # Show results preview
                st.subheader("Quiz Results Preview")
                prof_df = pd.read_csv(PROF_CSV_FILE)
                st.dataframe(prof_df)
            else:
                st.warning("No results available yet.")
            
            if st.button("Logout Professor"):
                st.session_state.prof_verified = False
                st.session_state.username = ""
                st.experimental_rerun()
    
    with tab2:  # Registration tab
        st.subheader("Professor Registration")
        
        # Hidden RRCE- prefix (completely invisible to users)
        prof_prefix = "RRCE-"
        
        # Display instruction about the prefix
        st.markdown("""
        <div style='background-color:#f0f2f6; padding:10px; border-radius:5px; margin-bottom:10px;'>
        <b>Note:</b> Your Professor ID will automatically start with <code></code>
        </div>
        """, unsafe_allow_html=True)
        
        # Input for the unique part only
        prof_id_suffix = st.text_input("Enter your unique ID suffix", 
                                     help="This will be combined with RRCE- to create your full Professor ID")
        
        # Combine prefix and suffix
        prof_id = f"{prof_prefix}{prof_id_suffix}"
        
        prof_email = st.text_input("Institutional Email", key="prof_email_reg")
        prof_pass = st.text_input("Create Password", type="password", key="prof_pass_reg")
        confirm_pass = st.text_input("Confirm Password", type="password", key="confirm_pass_reg")
        
        if st.button("Register as Professor"):
            # Validation checks
            if not prof_id_suffix:
                st.error("Please enter your unique ID suffix")
            elif not prof_email.endswith(".edu"):
                st.error("Please use your institutional email (.edu)")
            elif len(prof_pass) < 8:
                st.error("Password must be at least 8 characters")
            elif prof_pass != confirm_pass:
                st.error("Passwords do not match")
            else:
                # Check if professor ID already exists
                conn = get_db_connection()
                cursor = conn.execute("SELECT username FROM users WHERE username = ?", (prof_id,))
                if cursor.fetchone():
                    st.error("This Professor ID already exists")
                    conn.close()
                else:
                    conn.close()
                    # Send OTP for verification
                    otp = str(random.randint(100000, 999999))
                    if send_email_otp(prof_email, otp):
                        st.session_state['prof_otp'] = otp
                        st.session_state['prof_reg_data'] = (prof_id, prof_pass, "professor", prof_email)
                        st.success("OTP sent to your email!")
                    else:
                        st.error("Failed to send OTP")

elif choice == "View Recorded Video":
    st.subheader("Recorded Quiz Videos")
    video_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
    if video_files:
        selected_video = st.selectbox("Select a recorded video:", video_files)
        st.video(os.path.join(RECORDING_DIR, selected_video))
    else:
        st.warning("No recorded videos found.")
