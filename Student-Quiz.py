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
import cv2
import csv

# Initialize database and ensure tables exist
def init_db():
    conn = sqlite3.connect('quiz_app.db')
    cursor = conn.cursor()
    
    # Create users table if not exists
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    role TEXT DEFAULT 'student',
                    email TEXT)''')
    
    # Check if email column exists, if not add it
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if "email" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    
    # Create other tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                    username TEXT PRIMARY KEY,
                    change_count INTEGER DEFAULT 0)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                    username TEXT PRIMARY KEY,
                    attempt_count INTEGER DEFAULT 0)''')
    
    conn.commit()
    conn.close()

init_db()  # Initialize database when app starts

# Constants
PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recorded_videos"
os.makedirs(RECORDING_DIR, exist_ok=True)

# Session state initialization
for key in ["logged_in", "username", "camera_active", "prof_verified", "quiz_submitted", "usn", "section"]:
    if key not in st.session_state:
        st.session_state[key] = False if key not in ["username", "usn", "section"] else ""

# Database functions
def get_db_connection():
    return sqlite3.connect('quiz_app.db')

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role, email):
    conn = get_db_connection()
    try:
        # Check if username already exists
        cursor = conn.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            st.error("Username already exists! Please choose a different username.")
            return False
            
        # Check if email already exists
        cursor = conn.execute("SELECT email FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            st.error("Email already registered! Please use a different email.")
            return False
            
        # If username and email are unique, proceed with registration
        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                    (username, hash_password(password), role, email))
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        st.error(f"Registration failed: {str(e)}")
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user and user[0] == hash_password(password):
            return True
        return False
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return False
    finally:
        conn.close()

def get_user_role(username):
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
        role = cursor.fetchone()
        return role[0] if role else "student"
    finally:
        conn.close()

# Active student tracking
def add_active_student(username):
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                data = json.load(f)
        else:
            data = []
            
        if username not in data:
            data.append(username)
            with open(ACTIVE_FILE, "w") as f:
                json.dump(data, f)
    except Exception as e:
        st.error(f"Error adding active student: {e}")

def remove_active_student(username):
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                data = json.load(f)
            data = [u for u in data if u != username]
            with open(ACTIVE_FILE, "w") as f:
                json.dump(data, f)
    except:
        pass

def get_live_students():
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                return json.load(f)
        return []
    except:
        return []

# Email functions
def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = "rajkumar.k0322@gmail.com"
        msg['To'] = to_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

# Video recording functions
class VideoRecorder(VideoTransformerBase):
    def __init__(self):
        self.frames = []
        self.recording_started = False
        self.output_file = None
        
    def recv(self, frame):
        if not self.recording_started:
            # Ensure USN and section are available
            if hasattr(st.session_state, 'usn') and hasattr(st.session_state, 'section'):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.output_file = os.path.join(
                    RECORDING_DIR, 
                    f"{st.session_state.usn}_{st.session_state.section}_{timestamp}.mp4"
                )
                self.recording_started = True
            
        img = frame.to_ndarray(format="bgr24")
        self.frames.append(img)
        return frame
        
    def save_recording(self):
        if self.frames and self.output_file:
            height, width, _ = self.frames[0].shape
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(self.output_file, fourcc, 20.0, (width, height))
            for frame in self.frames:
                out.write(frame)
            out.release()
            
            # Save metadata
            log_path = os.path.join(RECORDING_DIR, "recordings_log.csv")
            with open(log_path, "a", newline="") as log_file:
                writer = csv.writer(log_file)
                writer.writerow([
                    os.path.basename(self.output_file),
                    st.session_state.usn,
                    st.session_state.section,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
            return self.output_file
        return None

# Question bank
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", 
     "options": ["%c", "%d", "%f", "%s"], 
     "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", 
     "options": ["while", "do-while", "for", "if"], 
     "answer": "for"},
]

# Main app
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", 
        "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Register New Account")
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    role = st.selectbox("Role", ["student"])

    if st.button("Send OTP"):
        if username and email and password:
            if password == confirm_password:
                # Check if username or email already exists before sending OTP
                conn = get_db_connection()
                try:
                    cursor = conn.execute("SELECT username FROM users WHERE username = ? OR email = ?", 
                                        (username, email))
                    existing_user = cursor.fetchone()
                    if existing_user:
                        if existing_user[0] == username:
                            st.error("Username already exists! Please choose a different username.")
                        else:
                            st.error("Email already registered! Please use a different email.")
                    else:
                        otp = str(random.randint(100000, 999999))
                        if send_email_otp(email, otp):
                            st.session_state['reg_otp'] = otp
                            st.session_state['reg_data'] = (username, password, role, email)
                            st.success("OTP sent to your email!")
                        else:
                            st.error("Failed to send OTP. Please try again.")
                finally:
                    conn.close()
            else:
                st.error("Passwords do not match!")
        else:
            st.error("Please fill all fields!")

    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if 'reg_otp' in st.session_state and otp_entered == st.session_state['reg_otp']:
            username, password, role, email = st.session_state['reg_data']
            if register_user(username, password, role, email):
                st.success("Registration successful! Please login.")
                del st.session_state['reg_otp']
                del st.session_state['reg_data']
            else:
                st.error("Registration failed. Please try again with different credentials.")
        else:
            st.error("Invalid OTP or registration data!")

    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if 'reg_otp' in st.session_state and otp_entered == st.session_state['reg_otp']:
            username, password, role, email = st.session_state['reg_data']
            if register_user(username, password, role, email):
                st.success("Registration successful! Please login.")
                del st.session_state['reg_otp']
                del st.session_state['reg_data']
        else:
            st.error("Invalid OTP or registration data!")

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        
        # Initialize session state variables if they don't exist
        if 'usn' not in st.session_state:
            st.session_state.usn = ""
        if 'section' not in st.session_state:
            st.session_state.section = ""
        
        # Only show USN/Section inputs if not already provided
        if not st.session_state.usn or not st.session_state.section:
            with st.form("quiz_start_form"):
                usn = st.text_input("Enter your USN")
                section = st.text_input("Enter your Section")
                if st.form_submit_button("Start Quiz"):
                    if usn and section:
                        st.session_state.usn = usn.strip().upper()
                        st.session_state.section = section.strip().upper()
                        st.session_state.camera_active = True
                        st.session_state.quiz_start_time = time.time()
                        st.rerun()
                    else:
                        st.error("Please enter both USN and Section")
            return  # Exit early if USN/section not provided yet
        
        # Rest of your quiz code...

    # Password reset functionality
    st.markdown("---")
    st.markdown("### Forgot Password?")
    reset_email = st.text_input("Enter your registered email")
    
    if st.button("Send Reset OTP"):
        conn = get_db_connection()
        try:
            cursor = conn.execute("SELECT username FROM users WHERE email = ?", (reset_email,))
            user = cursor.fetchone()
            if user:
                otp = str(random.randint(100000, 999999))
                if send_email_otp(reset_email, otp):
                    st.session_state['reset_otp'] = otp
                    st.session_state['reset_email'] = reset_email
                    st.session_state['reset_user'] = user[0]
                    st.success("OTP sent to your email!")
                else:
                    st.error("Failed to send OTP")
            else:
                st.error("Email not found in our system")
        finally:
            conn.close()

    if 'reset_otp' in st.session_state:
        st.markdown("### Reset Password")
        entered_otp = st.text_input("Enter the OTP you received")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        if st.button("Reset Password"):
            if entered_otp == st.session_state['reset_otp']:
                if new_password == confirm_password:
                    conn = get_db_connection()
                    try:
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                    (hash_password(new_password), st.session_state['reset_user']))
                        conn.commit()
                        st.success("Password reset successfully! Please login with your new password.")
                        del st.session_state['reset_otp']
                        del st.session_state['reset_email']
                        del st.session_state['reset_user']
                    except Exception as e:
                        st.error(f"Error resetting password: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("Passwords do not match!")
            else:
                st.error("Invalid OTP!")

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        
        if not st.session_state.get('usn') or not st.session_state.get('section'):
            with st.form("quiz_start_form"):
                usn = st.text_input("Enter your USN", key="usn_input")
                section = st.text_input("Enter your Section", key="section_input")
                if st.form_submit_button("Start Quiz"):
                    if usn and section:
                        st.session_state.usn = usn.strip().upper()
                        st.session_state.section = section.strip().upper()
                        st.session_state.camera_active = True
                        st.session_state.quiz_start_time = time.time()
                        st.session_state.video_recorder = VideoRecorder()
                        add_active_student(username)
                        st.rerun()
                    else:
                        st.error("Please enter both USN and Section")
        
        if st.session_state.get('usn') and st.session_state.get('section'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (username,))
                record = cursor.fetchone()
                attempt_count = record[0] if record else 0

                if attempt_count >= 2:
                    st.error("You have already taken the quiz 2 times. No more attempts allowed.")
                else:
                    # Timer
                    time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                    time_limit = 25 * 60  # 25 minutes
                    time_left = time_limit - time_elapsed

                    if time_left <= 0:
                        st.warning("⏰ Time is up! Auto-submitting your quiz.")
                        st.session_state.auto_submit = True
                    else:
                        mins, secs = divmod(time_left, 60)
                        st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")

                    # Webcam stream
                    if st.session_state.camera_active and not st.session_state.quiz_submitted:
                        st.markdown("<span style='color:red;'>🔴 Webcam is ON - Recording in progress</span>", unsafe_allow_html=True)
                        
                        # Initialize video processor only if USN and section are available
                        def get_video_processor():
                            if hasattr(st.session_state, 'video_recorder'):
                                return st.session_state.video_recorder
                            st.session_state.video_recorder = VideoRecorder()
                            return st.session_state.video_recorder
                        
                        webrtc_ctx = webrtc_streamer(
                            key="camera",
                            mode=WebRtcMode.SENDRECV,
                            media_stream_constraints={"video": True, "audio": False},
                            video_processor_factory=get_video_processor,
                            async_processing=True,
                        )

                    # Quiz questions
                    answers = {}
                    for idx, question in enumerate(QUESTIONS):
                        st.markdown(f"**Q{idx+1}:** {question['question']}")
                        ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                        answers[question['question']] = ans

                    # Submission
                    submit_btn = st.button("Submit Quiz")
                    auto_submit_triggered = st.session_state.get("auto_submit", False)

                    if (submit_btn or auto_submit_triggered) and not st.session_state.quiz_submitted:
                        if None in answers.values():
                            st.error("Please answer all questions before submitting the quiz.")
                        else:
                            # Calculate score
                            score = sum(1 for q in QUESTIONS if answers.get(q["question"]) == q["answer"])
                            time_taken = round(time.time() - st.session_state.quiz_start_time, 2)

                            # Save recording
                            if hasattr(st.session_state, 'video_recorder'):
                                video_file = st.session_state.video_recorder.save_recording()
                                if video_file:
                                    st.session_state.recorded_video = video_file

                            # Save results
                            new_row = pd.DataFrame([[
                                username, 
                                hash_password(username), 
                                st.session_state.usn, 
                                st.session_state.section, 
                                score, 
                                time_taken, 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ]], columns=["Username", "Hashed_Password", "USN", "Section", "Score", "Time_Taken", "Timestamp"])

                            # Save to professor CSV
                            if os.path.exists(PROF_CSV_FILE):
                                prof_df = pd.read_csv(PROF_CSV_FILE)
                                prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                            else:
                                prof_df = new_row
                            prof_df.to_csv(PROF_CSV_FILE, index=False)

                            # Save to section CSV
                            section_file = f"{st.session_state.section}_results.csv"
                            if os.path.exists(section_file):
                                sec_df = pd.read_csv(section_file)
                                sec_df = pd.concat([sec_df, new_row], ignore_index=True)
                            else:
                                sec_df = new_row
                            sec_df.to_csv(section_file, index=False)

                            # Update attempt count
                            if record:
                                conn.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                            else:
                                conn.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, ?)", (username, 1))
                            conn.commit()

                            # Email results
                            cursor = conn.execute("SELECT email FROM users WHERE username = ?", (username,))
                            email_record = cursor.fetchone()
                            if email_record and email_record[0]:
                                try:
                                    msg = EmailMessage()
                                    msg.set_content(f"""Hello {username},
                                    
You have completed the Secure Quiz with the following results:
- Score: {score}/{len(QUESTIONS)}
- Time Taken: {time_taken} seconds

Thank you for participating!""")
                                    msg['Subject'] = "Your Quiz Results"
                                    msg['From'] = "rajkumar.k0322@gmail.com"
                                    msg['To'] = email_record[0]

                                    server = smtplib.SMTP('smtp.gmail.com', 587)
                                    server.starttls()
                                    server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
                                    server.send_message(msg)
                                    server.quit()
                                    st.success("Quiz results have been emailed to you!")
                                except Exception as e:
                                    st.warning(f"Failed to send results email: {e}")

                            st.success(f"✅ Quiz submitted successfully! Your score: {score}/{len(QUESTIONS)}")
                            st.session_state.quiz_submitted = True
                            st.session_state.camera_active = False
                            remove_active_student(username)
            finally:
                conn.close()

elif choice == "Change Password":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        st.subheader("Change Password")
        old_pass = st.text_input("Current Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm New Password", type="password")
        
        if st.button("Change Password"):
            if not authenticate_user(st.session_state.username, old_pass):
                st.error("Current password is incorrect!")
            elif new_pass != confirm_pass:
                st.error("New passwords don't match!")
            else:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT change_count FROM password_changes WHERE username = ?", (st.session_state.username,))
                    record = cursor.fetchone()
                    
                    if record and record[0] >= 2:
                        st.error("You can only change your password twice!")
                    else:
                        # Update password
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                   (hash_password(new_pass), st.session_state.username))
                        
                        # Update change count
                        if record:
                            conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                       (st.session_state.username,))
                        else:
                            conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                       (st.session_state.username,))
                        
                        conn.commit()
                        st.success("Password changed successfully!")
                except Exception as e:
                    st.error(f"Error changing password: {e}")
                finally:
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
        
        # Results download
        if os.path.exists(PROF_CSV_FILE):
            with open(PROF_CSV_FILE, "rb") as file:
                st.download_button(
                    "\U0001F4E5 Download All Results (CSV)", 
                    file, 
                    "prof_quiz_results.csv", 
                    mime="text/csv"
                )
        else:
            st.warning("No quiz results available yet.")
        
        # Section-wise results
        st.markdown("---")
        st.subheader("Section-wise Results")
        section_files = [f for f in os.listdir() if f.endswith("_results.csv")]
        if section_files:
            selected_section = st.selectbox("Select Section", [f.replace("_results.csv", "") for f in section_files])
            section_file = f"{selected_section}_results.csv"
            if os.path.exists(section_file):
                df = pd.read_csv(section_file)
                st.dataframe(df)
                
                with open(section_file, "rb") as f:
                    st.download_button(
                        f"Download {selected_section} Results",
                        f,
                        f"{selected_section}_results.csv",
                        mime="text/csv"
                    )
        else:
            st.info("No section-wise results available yet.")

elif choice == "Professor Monitoring Panel":
    if not st.session_state.prof_verified:
        st.warning("Professor access only. Please login via 'Professor Panel' to verify.")
    else:
        st_autorefresh(interval=10 * 1000, key="monitor_refresh")
        st.header("\U0001F4E1 Live Student Monitoring")
        st.info("Students currently taking the quiz will appear here.")
        
        live_students = get_live_students()
        if not live_students:
            st.write("No active students currently taking the quiz.")
        else:
            for student in live_students:
                st.subheader(f"Student: {student}")
                st.write("Status: Active")
                
                # Show time elapsed
                conn = get_db_connection()
                try:
                    cursor = conn.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (student,))
                    attempt = cursor.fetchone()
                    st.write(f"Attempt: {attempt[0] + 1 if attempt else 1}")
                finally:
                    conn.close()

elif choice == "View Recorded Video":
    if not st.session_state.prof_verified:
        st.warning("Professor access only. Please login via 'Professor Panel' to verify.")
    else:
        st.subheader("Recorded Quiz Videos")
        
        log_path = os.path.join(RECORDING_DIR, "recordings_log.csv")
        if os.path.exists(log_path):
            try:
                df = pd.read_csv(log_path, names=["Filename", "USN", "Section", "Timestamp"])
                
                # Filter options
                col1, col2 = st.columns(2)
                with col1:
                    selected_section = st.selectbox("Filter by Section", ["All"] + list(df["Section"].unique()))
                with col2:
                    selected_usn = st.selectbox("Filter by USN", ["All"] + list(df["USN"].unique()))
                
                # Apply filters
                filtered = df.copy()
                if selected_section != "All":
                    filtered = filtered[filtered["Section"] == selected_section]
                if selected_usn != "All":
                    filtered = filtered[filtered["USN"] == selected_usn]
                
                if not filtered.empty:
                    selected_video = st.selectbox("Select Video", filtered["Filename"])
                    video_path = os.path.join(RECORDING_DIR, selected_video)
                    
                    if os.path.exists(video_path):
                        st.video(video_path)
                        
                        # Show metadata
                        video_info = filtered[filtered["Filename"] == selected_video].iloc[0]
                        st.write(f"USN: {video_info['USN']}")
                        st.write(f"Section: {video_info['Section']}")
                        st.write(f"Timestamp: {video_info['Timestamp']}")
                        
                        # Download button
                        with open(video_path, "rb") as f:
                            st.download_button(
                                "Download Video",
                                f,
                                selected_video,
                                mime="video/mp4"
                            )
                    else:
                        st.warning("Selected video file not found!")
                else:
                    st.warning("No recordings match your filters.")
            except Exception as e:
                st.error(f"Error loading recordings: {e}")
        else:
            st.warning("No recorded videos found in the system.")
