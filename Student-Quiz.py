import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import tempfile 
import cv2
import numpy as np
import moviepy.editor as mp
from gtts import gTTS
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
import av
from datetime import datetime
import smtplib
from email.message import EmailMessage
import random
import json
from streamlit_autorefresh import st_autorefresh
import shutil
import tempfile
from streamlit.runtime.scriptrunner import RerunData
from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.runtime.scriptrunner import RerunException

# Constants
EMAIL_SENDER = "rajkumar.k0322@gmail.com"
EMAIL_PASSWORD = "kcxf lzrq xnts xlng"  # App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
PROFESSOR_SECRET_KEY = "RRCE@123"
ACTIVE_FILE = "active_students.json"
PROF_CSV_FILE = "professor_results.csv"

# Use tempfile for all directories
VIDEO_DIR = os.path.join(tempfile.gettempdir(), "videos")
RECORDING_DIR = os.path.join(tempfile.gettempdir(), "recordings")
PHOTO_DIR = os.path.join(tempfile.gettempdir(), "student_photos")
CSV_FILE = os.path.join(tempfile.gettempdir(), "quiz_results.csv")

# Create directories safely
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(PHOTO_DIR, exist_ok=True)

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'role' not in st.session_state:
    st.session_state.role = ""
if 'camera_active' not in st.session_state:
    st.session_state.camera_active = False
if 'prof_verified' not in st.session_state:
    st.session_state.prof_verified = False
if 'quiz_submitted' not in st.session_state:
    st.session_state.quiz_submitted = False
if 'usn' not in st.session_state:
    st.session_state.usn = ""
if 'section' not in st.session_state:
    st.session_state.section = ""
if 'prof_dir' not in st.session_state:
    st.session_state.prof_dir = "professor_data"

def get_db_connection():
    try:
        conn = sqlite3.connect('quiz_app.db', check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency handling
        return conn
    except sqlite3.Error as e:
        st.error(f"Database connection error: {e}")
        raise

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            email TEXT
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            username TEXT PRIMARY KEY,
            attempt_count INTEGER DEFAULT 0,
            FOREIGN KEY(username) REFERENCES users(username)
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS password_changes (
            username TEXT PRIMARY KEY,
            change_count INTEGER DEFAULT 0,
            FOREIGN KEY(username) REFERENCES users(username)
        )""")
        
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database initialization error: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Call this at the start of your application, right after imports
init_db()

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role, email):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username already exists
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            st.error("Username already exists!")
            return False
            
        # Insert new user
        cursor.execute(
            "INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)", 
            (username, hash_password(password), role, email)
        )

        conn.commit()
        st.success("Registration successful! Please login.")
        return True
        
    except sqlite3.Error as e:
        st.error(f"Database error during registration: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def authenticate_user(username, password):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        return user[0] == hash_password(password) if user else False
    except sqlite3.Error as e:
        st.error(f"Authentication error: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def get_user_role(username):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
        role = cursor.fetchone()
        return role[0] if role else "student"
    except sqlite3.Error as e:
        st.error(f"Error getting user role: {str(e)}")
        return "student"
    finally:
        if conn:
            conn.close()

def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

def add_active_student(username):
    """Adds student to active list"""
    try:
        active = []
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                active = json.load(f)
        
        if username not in active:
            active.append(username)
            with open(ACTIVE_FILE, "w") as f:
                json.dump(active, f)
    except Exception as e:
        st.error(f"Error adding student: {str(e)}")

def remove_active_student(username):
    """Removes student from active list"""
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                active = json.load(f)
            
            active = [u for u in active if u != username]
            
            with open(ACTIVE_FILE, "w") as f:
                json.dump(active, f)
    except Exception as e:
        st.error(f"Error removing student: {str(e)}")

def get_live_students():
    """Returns list of active students from JSON file"""
    if os.path.exists(ACTIVE_FILE):
        with open(ACTIVE_FILE, "r") as f:
            return json.load(f)
    return []

# Quiz questions
QUESTIONS = [
    {"question": "🔤 Which data type is used to store a single character in C? 🎯", "options": ["char", "int", "float", "double"], "answer": "char"},
    {"question": "🔢 What is the output of 5 / 2 in C if both operands are integers? ⚡", "options": ["2.5", "2", "3", "Error"], "answer": "2"},
    {"question": "🔁 Which loop is used when the number of iterations is known? 🔄", "options": ["while", "do-while", "for", "if"], "answer": "for"},
    {"question": "📌 What is the format specifier for printing an integer in C? 🖨️", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"}]

def generate_audio(question_text, filename):
    try:
        if not os.path.exists(filename):
            tts = gTTS(text=question_text, lang='en')
            tts.save(filename)
    except Exception as e:
        st.error(f"Error generating audio: {str(e)}")

def create_video(question_text, filename, audio_file):
    try:
        video_path = os.path.join(VIDEO_DIR, filename)
        
        # Create directory if it doesn't exist
        os.makedirs(VIDEO_DIR, exist_ok=True)
        
        # Check if video already exists
        if os.path.exists(video_path):
            return video_path

        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_video_path = os.path.join(temp_dir, "temp_video.mp4")
            temp_audio_path = os.path.join(temp_dir, "temp_audio.mp3")
            
            # Step 1: Create silent video
            width, height = 640, 480
            img = np.full((height, width, 3), (255, 223, 186), dtype=np.uint8)
            font = cv2.FONT_HERSHEY_SIMPLEX

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_video_path, fourcc, 10, (width, height))

            for _ in range(50):  # 5 seconds of video at 10fps
                img_copy = img.copy()
                text_size = cv2.getTextSize(question_text, font, 1, 2)[0]
                text_x = (width - text_size[0]) // 2
                text_y = (height + text_size[1]) // 2
                cv2.putText(img_copy, question_text, (text_x, text_y), font, 1, (0, 0, 255), 2, cv2.LINE_AA)
                out.write(img_copy)
            out.release()

            # Step 2: Copy audio to temp location
            shutil.copy(audio_file, temp_audio_path)

            # Step 3: Combine video and audio
            try:
                video_clip = mp.VideoFileClip(temp_video_path)
                audio_clip = mp.AudioFileClip(temp_audio_path)
                
                # Ensure audio duration matches video
                if audio_clip.duration > video_clip.duration:
                    audio_clip = audio_clip.subclip(0, video_clip.duration)
                
                final_video = video_clip.set_audio(audio_clip)
                
                # Write final video directly to target location
                final_video.write_videofile(
                    video_path,
                    codec='libx264',
                    fps=10,
                    audio_codec='aac',
                    threads=4,
                    logger=None  # Disable verbose output
                )
                
                # Explicitly close clips to release resources
                video_clip.close()
                audio_clip.close()
                final_video.close()
                
                return video_path
                
            except Exception as e:
                st.error(f"Error combining video and audio: {str(e)}")
                return None
                
    except Exception as e:
        st.error(f"Error creating video: {str(e)}")
        return None

def rerun():
    """Programmatically rerun the Streamlit app"""
    ctx = get_script_run_ctx()
    if ctx:
        raise RerunException(RerunData())

class VideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.recording = True
        self.frames = []
        self.start_time = time.time()
        self.last_save_time = time.time()
        
    def recv(self, frame):
        try:
            img = frame.to_ndarray(format="bgr24")
            
            # Record at reduced frame rate (every 3rd frame)
            if self.recording and len(self.frames) % 3 == 0:
                self.frames.append(img)
                
            # Auto-save every 20 seconds
            current_time = time.time()
            if current_time - self.last_save_time > 20 and self.frames:
                self._save_recording()
                self.last_save_time = current_time
                self.frames = []  # Clear buffer after saving
                
            return av.VideoFrame.from_ndarray(img, format="bgr24")
        except Exception as e:
            st.error(f"Camera error: {str(e)}")
            return frame
            
    def _save_recording(self):
        if not self.frames:
            return
            
        try:
            height, width, _ = self.frames[0].shape
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_path = os.path.join(RECORDING_DIR, f"quiz_recording_{timestamp}.mp4")
            
            os.makedirs(RECORDING_DIR, exist_ok=True)
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_path, fourcc, 10, (width, height))
            
            for frame in self.frames:
                out.write(frame)
            out.release()
            
        except Exception as e:
            st.error(f"Failed to save recording: {str(e)}")

    def close(self):
        self._save_recording()

# Streamlit UI
st.title("🎥 Interactive Video Quiz 🎬")

# UI Starts
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recordings"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Register")
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    
    if st.button("Send OTP"):
        if username and email and password:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(email, otp):
                st.session_state['reg_otp'] = otp
                st.session_state['reg_data'] = (username, password, email)
                st.success("OTP sent to your email.")
            else:
                st.error("Failed to send OTP. Please try again.")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if 'reg_otp' in st.session_state and otp_entered == st.session_state['reg_otp']:
            username, password, email = st.session_state['reg_data']
            if register_user(username, password, "student", email):
                del st.session_state['reg_otp']
                del st.session_state['reg_data']
                st.success("Registration successful! Please login.")
        else:
            st.error("Incorrect OTP or OTP not requested!")

elif choice == "Login":
    st.subheader("Login")

    if 'login_username' not in st.session_state:
        st.session_state.login_username = ""
    if 'login_password' not in st.session_state:
        st.session_state.login_password = ""

    username = st.text_input("Username", value=st.session_state.login_username, key="login_username_widget")
    password = st.text_input("Password", type="password", value=st.session_state.login_password, key="login_password_widget")
    
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = get_user_role(username)
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
                    try:
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                  (hash_password(new_password), st.session_state['reset_user']))
                        
                        cursor = conn.execute("SELECT password FROM users WHERE username = ?",
                                             (st.session_state['reset_user'],))
                        updated_password = cursor.fetchone()[0]
                        
                        if updated_password == hash_password(new_password):
                            cursor = conn.execute("SELECT change_count FROM password_changes WHERE username = ?",
                                                (st.session_state['reset_user'],))
                            record = cursor.fetchone()
                            
                            if record:
                                conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                           (st.session_state['reset_user'],))
                            else:
                                conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                           (st.session_state['reset_user'],))
                            
                            conn.commit()
                            
                            st.session_state.login_username = st.session_state['reset_user']
                            st.session_state.login_password = new_password
                            
                            st.success("Password reset successfully! Your credentials have been filled below. Click Login to continue.")
                            
                            for key in ['reset_otp', 'reset_email', 'reset_user']:
                                if key in st.session_state:
                                    del st.session_state[key]
                            
                            st.rerun()
                        else:
                            st.error("Password update failed. Please try again.")
                    except Exception as e:
                        st.error(f"Error updating password: {str(e)}")
                    finally:
                        conn.close()
                else:
                    st.error("Passwords do not match. Please try again.")
            else:
                st.error("Incorrect OTP. Please try again.")

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        usn = st.text_input("Enter your USN")
        section = st.text_input("Enter your Section")
        st.session_state.usn = usn.strip().upper()
        st.session_state.section = section.strip().upper()
        if "quiz_active" not in st.session_state:
            add_active_student(st.session_state.username)  # <-- ADD THIS LINE
            st.session_state.quiz_active = True
        if usn and section:
            conn = None
            try:
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

                    time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                    time_limit = 25 * 60  # 25 minutes
                    time_left = time_limit - time_elapsed

                    if time_left <= 0:
                        st.warning("⏰ Time is up! Auto-submitting your quiz.")
                        st.session_state.auto_submit = True
                    else:
                        mins, secs = divmod(time_left, 60)
                        st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")

                    # Take verification photo
                    st.markdown("### Verification Photo")
                    img_file_buffer = st.camera_input("Take a verification photo")
                    
                    if img_file_buffer is not None:
                        try:
                            os.makedirs(PHOTO_DIR, exist_ok=True)
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            img_path = os.path.join(PHOTO_DIR, f"{username}_{st.session_state.usn}_{timestamp}.jpg")
                            
                            with open(img_path, "wb") as f:
                                f.write(img_file_buffer.getvalue())
                            st.success("✅ Verification photo saved!")
                        except Exception as e:
                            st.error(f"Failed to save photo: {str(e)}")

                    answers = {}
                    for idx, question in enumerate(QUESTIONS):
                        question_text = question["question"]
    
                        audio_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp3")
                        if not os.path.exists(audio_file):
                            try:
                                tts = gTTS(text=question_text, lang='en', slow=False)
                                tts.save(audio_file)
                            except Exception as e:
                                st.error(f"Error generating audio: {str(e)}")
                                st.markdown(f"**Q{idx+1}:** {question_text}")
                                ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                                continue
                        
                        video_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp4")
                        final_video_path = create_video(question_text, f"question_{idx}_final.mp4", audio_file)
                        
                        if final_video_path and os.path.exists(final_video_path):
                            try:
                                st.video(final_video_path)
                            except Exception as e:
                                st.error(f"Error displaying video: {str(e)}")
                                st.markdown(f"**Q{idx+1}:** {question_text}")
                        else:
                            st.markdown(f"**Q{idx+1}:** {question_text}")
                        
                        ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                        answers[question['question']] = ans

                    if st.button("Submit Quiz"):
                        remove_active_student(st.session_state.username)
                        if None in answers.values():
                            st.error("Please answer all questions before submitting the quiz.")
                        else:
                            try:
                                # Calculate score
                                score = 0
                                for q in QUESTIONS:
                                    if answers.get(q["question"]) == q["answer"]:
                                        score += 1
                                
                                time_taken = round(time.time() - st.session_state.quiz_start_time, 2)
                    
                                # Save results
                                new_row = pd.DataFrame([[username, hash_password(username), st.session_state.usn, 
                                                       st.session_state.section, score, time_taken, datetime.now()]],
                                                     columns=["Username", "Hashed_Password", "USN", "Section", 
                                                             "Score", "Time_Taken", "Timestamp"])
                    
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
                    
                                # Update attempts
                                if record:
                                    cur.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                                else:
                                    cur.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, ?)", (username, 1))
                                conn.commit()
                    
                                # Send email confirmation
                                email_result = conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                                if email_result:
                                    try:
                                        msg = EmailMessage()
                                        msg.set_content(f"""Dear {username},
                                        
You have successfully submitted your quiz.
Score: {score}/{len(QUESTIONS)}
Time Taken: {time_taken} seconds

Thank you for participating.""")
                                        msg['Subject'] = "Quiz Submission Confirmation"
                                        msg['From'] = EMAIL_SENDER
                                        msg['To'] = email_result[0]
                    
                                        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                                            server.starttls()
                                            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                                            server.send_message(msg)
                                    except Exception as e:
                                        st.error(f"Result email failed: {e}")
                    
                                st.session_state.quiz_submitted = True
                                st.success(f"Quiz submitted successfully! Your score is {score}/{len(QUESTIONS)}")
                                st.success("Quiz submitted successfully! check Your Mail")
                                st.balloons()
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error saving results: {str(e)}")
            except sqlite3.Error as e:
                st.error(f"Database error: {str(e)}")
            finally:
                if conn:
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
    
    if 'prof_secret_verified' not in st.session_state:
        secret_key = st.text_input("Enter Professor Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_secret_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        tab1, tab2 = st.tabs(["Professor Login", "Professor Registration"])
        
        with tab1:
            if not st.session_state.get('prof_logged_in', False):
                prof_id = st.text_input("Professor ID")
                prof_pass = st.text_input("Professor Password", type="password")
                
                if st.button("Login as Professor"):
                    conn = get_db_connection()
                    cursor = conn.execute("SELECT password, role, email FROM users WHERE username = ? AND role = 'professor'", 
                                        (prof_id,))
                    prof_data = cursor.fetchone()
                    conn.close()
                    
                    if prof_data and prof_data[0] == hash_password(prof_pass):
                        st.session_state.prof_logged_in = True
                        st.session_state.username = prof_id
                        st.session_state.role = "professor"
                        st.success(f"Welcome Professor {prof_id}!")
                        os.makedirs(st.session_state.prof_dir, exist_ok=True)
                        st.rerun()
                    else:
                        st.error("Invalid Professor credentials")
            else:
                st.success(f"Welcome Professor {st.session_state.username}!")
                st.subheader("Student Results Management")
                
                result_files = []
                if os.path.exists(PROF_CSV_FILE):
                    result_files.append(PROF_CSV_FILE)
                
                section_files = [f for f in os.listdir() if f.endswith("_results.csv")]
                result_files.extend(section_files)
                
                if result_files:
                    selected_file = st.selectbox("Select results file", result_files)
                    try:
                        df = pd.read_csv(selected_file)
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Students", len(df))
                        with col2:
                            avg_score = df['Score'].mean()
                            st.metric("Average Score", f"{avg_score:.1f}/{len(QUESTIONS)}")
                        with col3:
                            pass_rate = (len(df[df['Score'] >= len(QUESTIONS)/2]) / len(df)) * 100
                            st.metric("Pass Rate", f"{pass_rate:.1f}%")

                        st.markdown("### Detailed Results")
                        sort_by = st.selectbox("Sort by", ["Score", "Time_Taken", "Timestamp", "Section"])
                        ascending = st.checkbox("Ascending order", True)
                        sorted_df = df.sort_values(by=sort_by, ascending=ascending)
                        st.dataframe(sorted_df)
                        
                        st.download_button(
                            label="Download Results",
                            data=sorted_df.to_csv(index=False),
                            file_name=f"sorted_{selected_file}",
                            mime="text/csv"
                        )
                        
                    except Exception as e:
                        st.error(f"Error loading results: {e}")
                else:
                    st.warning("No results available yet.")
                
                if st.button("Logout"):
                    st.session_state.prof_logged_in = False
                    st.session_state.username = ""
                    st.session_state.role = ""
                    st.rerun()
        
        with tab2:
            st.subheader("Professor Registration")
            st.warning("Professor accounts require verification.")
            
            full_name = st.text_input("Full Name")
            designation = st.text_input("Designation")
            department = st.selectbox("Department", ["CSE", "ISE", "ECE", "EEE", "MECH", "CIVIL"])
            institutional_email = st.text_input("Institutional Email")
            
            if st.button("Request Account"):
                if full_name and designation and department and institutional_email:
                    prof_id = f"PROF-{random.randint(10000, 99999)}"
                    temp_password = str(random.randint(100000, 999999))
                    
                    conn = get_db_connection()
                    try:
                        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                                    (prof_id, hash_password(temp_password), "professor", institutional_email))
                        conn.commit()
                        
                        os.makedirs(f"professor_data/{prof_id}", exist_ok=True)
                        
                        try:
                            msg = EmailMessage()
                            msg.set_content(f"""Dear {full_name},

Your professor account has been created:

Username: {prof_id}
Password: {temp_password}

Please login and change your password immediately.

Regards,
Quiz App Team""")
                            msg['Subject'] = "Professor Account Credentials"
                            msg['From'] = EMAIL_SENDER
                            msg['To'] = institutional_email

                            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                            server.starttls()
                            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                            server.send_message(msg)
                            server.quit()
                            
                            st.success("Account created! Credentials sent to your email.")
                        except Exception as e:
                            st.error(f"Account created but email failed: {e}")
                    except sqlite3.IntegrityError:
                        st.error("Professor with this email already exists!")
                    finally:
                        conn.close()
                else:
                    st.error("Please fill all fields!")

elif choice == "Professor Monitoring Panel":
    if not st.session_state.get('prof_verified', False):
        secret_key = st.text_input("Enter Professor Secret Key", type="password")
        if st.button("Verify") and secret_key == PROFESSOR_SECRET_KEY:
            st.session_state.prof_verified = True
            st.rerun()
    else:
        st_autorefresh(interval=3000, key="monitor_refresh")  # Refresh every 3 sec
        
        st.header("👥 Active Quiz Takers")
        try:
            active_students = []
            if os.path.exists(ACTIVE_FILE):
                with open(ACTIVE_FILE, "r") as f:
                    active_students = json.load(f)
            
            if not active_students:
                st.warning("No students currently taking the quiz")
            else:
                for student in active_students:
                    st.success(f"• {student}")
        
        except Exception as e:
            st.error(f"Monitoring error: {str(e)}")
elif choice == "View Recordings":
    if not st.session_state.get('recordings_verified', False):
        secret_key = st.text_input("Enter Professor Secret Key to view recordings", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.recordings_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        st.subheader("Recorded Sessions")
        
        tab1, tab2 = st.tabs(["Videos", "Photos"])
        
        with tab1:
            st.markdown("### Video Recordings")
            try:
                video_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
                
                if video_files:
                    selected_video = st.selectbox("Select a video recording", video_files)
                    video_path = os.path.join(RECORDING_DIR, selected_video)
                    st.video(video_path)
                    
                    if st.button("Delete Selected Video"):
                        try:
                            os.remove(video_path)
                            st.success("Video deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting video: {str(e)}")
                else:
                    st.warning("No video recordings available.")
            except Exception as e:
                st.error(f"Error accessing video recordings: {str(e)}")
        
        with tab2:
            st.markdown("### Student Verification Photos")
            try:
                photo_files = [f for f in os.listdir(PHOTO_DIR) if f.endswith(".jpg")]
                
                if photo_files:
                    selected_photo = st.selectbox("Select a photo", photo_files)
                    photo_path = os.path.join(PHOTO_DIR, selected_photo)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.image(photo_path, caption=selected_photo, use_column_width=True)
                    
                    with col2:
                        st.write("Photo Details:")
                        parts = selected_photo.split('_')
                        if len(parts) >= 3:
                            st.write(f"Username: {parts[0]}")
                            st.write(f"USN: {parts[1]}")
                            st.write(f"Timestamp: {'_'.join(parts[2:]).replace('.jpg', '')}")
                        else:
                            st.write("Unable to extract photo details.")

                    if st.button("Delete Selected Photo"):
                        try:
                            os.remove(photo_path)
                            st.success("Photo deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting photo: {str(e)}")
                else:
                    st.warning("No student verification photos available.")
            except Exception as e:
                st.error(f"Error accessing photos: {str(e)}")

        if st.button("Exit Recordings Panel"):
            st.session_state.recordings_verified = False
            st.rerun()
