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

# Configuration
PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
os.makedirs(RECORDING_DIR, exist_ok=True)

# Email configuration
EMAIL_SENDER = "rajkumar.k0322@gmail.com"
EMAIL_PASSWORD = "kcxf lzrq xnts xlng"  # App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Secret key for professor panel
PROFESSOR_SECRET_KEY = "RRCE@123"

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'role' not in st.session_state:  # Added role to session state
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

# Database functions
def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    role TEXT DEFAULT 'student',
                    email TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                    username TEXT PRIMARY KEY,
                    change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                    username TEXT PRIMARY KEY,
                    attempt_count INTEGER DEFAULT 0)''')
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

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
    cursor = conn.execute("SELECT password, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return user[0] == hash_password(password), user[1]  # Return both password match and role
    return False, None

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
    except (FileNotFoundError, json.JSONDecodeError):
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
    except (FileNotFoundError, json.JSONDecodeError):
        pass

def get_live_students():
    try:
        with open(ACTIVE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# Question bank
QUESTIONS = [
    {
        "question": "What is the format specifier for an integer in C?",
        "options": ["%c", "%d", "%f", "%s"],
        "answer": "%d"
    },
    {
        "question": "Which loop is used when the number of iterations is known?",
        "options": ["while", "do-while", "for", "if"],
        "answer": "for"
    },
]

class VideoProcessor(VideoTransformerBase):
    def recv(self, frame):
        return frame

# Main UI
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("User Registration")
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["student"])

    if st.button("Send OTP"):
        if username and email and password:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(email, otp):
                st.session_state['reg_otp'] = otp
                st.session_state['reg_data'] = (username, password, role, email)
                st.success("OTP sent to your email.")
            else:
                st.error("Failed to send OTP. Please try again.")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if 'reg_otp' not in st.session_state or 'reg_data' not in st.session_state:
            st.error("Please request an OTP first.")
        elif otp_entered == st.session_state['reg_otp']:
            username, password, role, email = st.session_state['reg_data']
            register_user(username, password, role, email)
            del st.session_state['reg_otp']
            del st.session_state['reg_data']
        else:
            st.error("Incorrect OTP!")

# ... [Previous imports and configuration remain the same until the Login section] ...

elif choice == "Login":
    st.subheader("Login")

    # ---------- Login Form ----------
    username = st.text_input("Username", key="login_username").strip()
    password = st.text_input("Password", type="password", key="login_password").strip()
    
    if st.button("Login"):
        if username and password:
            conn = get_db_connection()
            cursor = conn.execute("SELECT password, role FROM users WHERE username = ?", (username,))
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data and user_data[0] == hash_password(password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = user_data[1]
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password. Please try again.")
        else:
            st.warning("Please enter both username and password")

    # ---------- Forgot Password ----------
    st.markdown("### Forgot Password?")
    forgot_email = st.text_input("Enter registered email", key="forgot_email_input").strip()
    
    if st.button("Send Reset OTP"):
        if forgot_email:
            conn = get_db_connection()
            user = conn.execute("SELECT username, email FROM users WHERE email = ?", (forgot_email,)).fetchone()
            conn.close()

            if user:
                otp = str(random.randint(100000, 999999))
                if send_email_otp(user[1], otp):
                    st.session_state['reset_email'] = user[1]
                    st.session_state['reset_otp'] = otp
                    st.session_state['reset_user'] = user[0]
                    st.success("OTP sent to your email.")
                else:
                    st.error("Failed to send OTP. Please try again.")
            else:
                st.error("Email not found in our system.")
        else:
            st.warning("Please enter your registered email")

    # ---------- Reset Password ----------
    if 'reset_otp' in st.session_state:
        st.markdown("### Reset Your Password")
        entered_otp = st.text_input("Enter OTP", key="reset_otp_input").strip()
        new_password = st.text_input("New Password", type="password", key="reset_new_password").strip()
        confirm_password = st.text_input("Confirm Password", type="password", key="reset_confirm_password").strip()

        if st.button("Reset Password"):
            if not all([entered_otp, new_password, confirm_password]):
                st.warning("Please fill all fields")
            elif entered_otp != st.session_state['reset_otp']:
                st.error("Invalid OTP!")
            elif new_password != confirm_password:
                st.error("Passwords do not match!")
            else:
                conn = get_db_connection()
                try:
                    # Update password in database
                    conn.execute("UPDATE users SET password = ? WHERE username = ?",
                               (hash_password(new_password), st.session_state['reset_user']))
                    conn.commit()
                    
                    # Clear password change restrictions
                    conn.execute("DELETE FROM password_changes WHERE username = ?",
                               (st.session_state['reset_user'],))
                    conn.commit()
                    
                    # Verify the password was updated
                    cursor = conn.execute("SELECT password FROM users WHERE username = ?",
                                        (st.session_state['reset_user'],))
                    updated_password = cursor.fetchone()[0]
                    
                    if updated_password == hash_password(new_password):
                        # Automatically log user in
                        st.session_state.logged_in = True
                        st.session_state.username = st.session_state['reset_user']
                        cursor = conn.execute("SELECT role FROM users WHERE username = ?",
                                            (st.session_state['reset_user'],))
                        role = cursor.fetchone()
                        st.session_state.role = role[0] if role else "student"
                        
                        st.success("Password reset successful! You are now logged in.")
                        
                        # Clear reset session state
                        for key in ['reset_otp', 'reset_email', 'reset_user']:
                            if key in st.session_state:
                                del st.session_state[key]
                    else:
                        st.error("Password update failed. Please try again.")
                    
                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                finally:
                    conn.close()
                    st.rerun()

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        st.subheader(f"Quiz for {username}")
        usn = st.text_input("Enter your USN").strip().upper()
        section = st.text_input("Enter your Section").strip().upper()
        st.session_state.usn = usn
        st.session_state.section = section

        if usn and section:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (username,))
            record = cur.fetchone()
            attempt_count = record[0] if record else 0
            conn.close()

            if attempt_count >= 2:
                st.error("You have already taken the quiz 2 times. No more attempts allowed.")
            else:
                if "quiz_start_time" not in st.session_state:
                    st.session_state.quiz_start_time = time.time()
                    st.session_state.answers = {}
                    add_active_student(username)
                    st.session_state.camera_active = True

                time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                time_limit = 25 * 60
                time_left = max(0, time_limit - time_elapsed)
                
                mins, secs = divmod(time_left, 60)
                st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")
                
                if time_left <= 0:
                    st.warning("⏰ Time is up! Auto-submitting your quiz.")
                    st.session_state.auto_submit = True

                if st.session_state.camera_active and not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_streamer(
                        key="quiz_camera",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={"video": True, "audio": False},
                        video_processor_factory=VideoProcessor,
                    )

                for idx, question in enumerate(QUESTIONS):
                    st.markdown(f"**Q{idx+1}:** {question['question']}")
                    ans = st.radio(f"Select answer for Q{idx+1}:", 
                                   question['options'], 
                                   key=f"q{idx}", 
                                   index=None)
                    st.session_state.answers[question['question']] = ans

                submit_btn = st.button("Submit Quiz")
                auto_submit_triggered = st.session_state.get("auto_submit", False)
                
                if (submit_btn or auto_submit_triggered) and not st.session_state.quiz_submitted:
                    if None in st.session_state.answers.values():
                        st.error("Please answer all questions before submitting.")
                    else:
                        score = 0
                        for q in QUESTIONS:
                            if st.session_state.answers.get(q["question"]) == q["answer"]:
                                score += 1
                        
                        time_taken = round(time.time() - st.session_state.quiz_start_time, 2)
                        new_row = pd.DataFrame([[username, st.session_state.usn, st.session_state.section, 
                                               score, time_taken, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]],
                                             columns=["Username", "USN", "Section", "Score", "Time_Taken", "Timestamp"])
                        
                        if os.path.exists(PROF_CSV_FILE):
                            prof_df = pd.read_csv(PROF_CSV_FILE)
                            prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                        else:
                            prof_df = new_row
                        prof_df.to_csv(PROF_CSV_FILE, index=False)
                        
                        section_file = f"{section}_results.csv"
                        if os.path.exists(section_file):
                            sec_df = pd.read_csv(section_file)
                            sec_df = pd.concat([sec_df, new_row], ignore_index=True)
                        else:
                            sec_df = new_row
                        sec_df.to_csv(section_file, index=False)
                        
                        conn = get_db_connection()
                        if record:
                            conn.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", 
                                        (username,))
                        else:
                            conn.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, 1)", 
                                        (username,))
                        conn.commit()
                        
                        email_result = conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                        conn.close()
                        
                        if email_result and email_result[0]:
                            try:
                                msg = EmailMessage()
                                msg.set_content(f"""Dear {username},
Your quiz results:
Score: {score}/{len(QUESTIONS)}
Time Taken: {time_taken} seconds""")
                                msg['Subject'] = "Your Quiz Results"
                                msg['From'] = EMAIL_SENDER
                                msg['To'] = email_result[0]

                                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                                server.starttls()
                                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                                server.send_message(msg)
                                server.quit()
                            except Exception as e:
                                st.warning(f"Couldn't send results email: {str(e)}")
                        
                        st.session_state.quiz_submitted = True
                        st.session_state.camera_active = False
                        remove_active_student(username)
                        st.success(f"Quiz submitted! and result's sent Your score on Mail: {score}/{len(QUESTIONS)}")

elif choice == "Change Password":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        st.subheader("Change Password")
        username = st.session_state.username
        old_pass = st.text_input("Current Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm New Password", type="password")
        
        if st.button("Change Password"):
            if not authenticate_user(username, old_pass)[0]:  # Updated to use tuple unpacking
                st.error("Current password is incorrect!")
            elif new_pass != confirm_pass:
                st.error("New passwords don't match!")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT change_count FROM password_changes WHERE username = ?", (username,))
                record = cursor.fetchone()
                
                if record and record[0] >= 2:
                    st.error("You can only change password twice!")
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
                    st.success("Password changed successfully!")
                conn.close()

elif choice == "Professor Panel":
    st.subheader("\U0001F9D1‍\U0001F3EB Professor Access Panel")
    
    # First check for secret key
    if 'prof_secret_verified' not in st.session_state:
        secret_key = st.text_input("Enter Professor Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_secret_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        # After secret key verification, show login/registration tabs
        tab1, tab2 = st.tabs(["Professor Login", "Professor Registration"])
        
        with tab1:  # Login tab
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
                # Show professor dashboard after successful login
                st.success(f"Welcome Professor {st.session_state.username}!")
                st.subheader("Student Results Management")
                
                # View results section
                result_files = []
                if os.path.exists(PROF_CSV_FILE):
                    result_files.append(PROF_CSV_FILE)
                
                # Check for section-wise files
                section_files = [f for f in os.listdir() if f.endswith("_results.csv")]
                result_files.extend(section_files)
                
                if result_files:
                    selected_file = st.selectbox("Select results file", result_files)
                    try:
                        df = pd.read_csv(selected_file)
                        
                        # Display statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Students", len(df))
                        with col2:
                            avg_score = df['Score'].mean()
                            st.metric("Average Score", f"{avg_score:.1f}/{len(QUESTIONS)}")
                        with col3:
                            pass_rate = (len(df[df['Score'] >= len(QUESTIONS)/2]) / len(df)) * 100
                            st.metric("Pass Rate", f"{pass_rate:.1f}%")

                        # Show full results
                        st.markdown("### Detailed Results")
                        sort_by = st.selectbox("Sort by", ["Score", "Time_Taken", "Timestamp", "Section"])
                        ascending = st.checkbox("Ascending order", True)
                        sorted_df = df.sort_values(by=sort_by, ascending=ascending)
                        st.dataframe(sorted_df)
                        
                        # Download option
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
                
                # Logout button
                if st.button("Logout"):
                    st.session_state.prof_logged_in = False
                    st.session_state.username = ""
                    st.session_state.role = ""
                    st.rerun()
        
        with tab2:  # Registration tab
            st.subheader("Professor Registration")
            st.warning("Professor accounts require verification.")
            
            # Registration form
            full_name = st.text_input("Full Name")
            designation = st.text_input("Designation")
            department = st.selectbox("Department", ["CSE", "ISE", "ECE", "EEE", "MECH", "CIVIL"])
            institutional_email = st.text_input("Institutional Email")
            
            if st.button("Request Account"):
                if full_name and designation and department and institutional_email:
                    # Generate credentials
                    prof_id = f"PROF-{random.randint(10000, 99999)}"
                    temp_password = str(random.randint(100000, 999999))
                    
                    # Register professor
                    conn = get_db_connection()
                    try:
                        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                                    (prof_id, hash_password(temp_password), "professor", institutional_email))
                        conn.commit()
                        
                        # Create directory
                        os.makedirs(f"professor_data/{prof_id}", exist_ok=True)
                        
                        # Send credentials
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
        secret_key = st.text_input("Enter Professor Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        st_autorefresh(interval=10000, key="monitor_refresh")
        st.header("\U0001F4E1 Live Monitoring Dashboard")
        st.info("Monitoring students currently taking the quiz")
        
        live_students = get_live_students()
        if not live_students:
            st.write("No active students at the moment.")
        else:
            st.write(f"Active students ({len(live_students)}):")
            for student in live_students:
                st.write(f"- {student}")
                
            st.markdown("---")
            st.markdown("### Recent Quiz Submissions")
            if os.path.exists(PROF_CSV_FILE):
                df = pd.read_csv(PROF_CSV_FILE)
                recent_submissions = df.sort_values("Timestamp", ascending=False).head(5)
                st.dataframe(recent_submissions)
            else:
                st.warning("No quiz submissions yet.")

elif choice == "View Recorded Video":
    st.subheader("Recorded Sessions")
    video_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
    
    if video_files:
        selected_video = st.selectbox("Select recording", video_files)
        video_path = os.path.join(RECORDING_DIR, selected_video)
        st.video(video_path)
    else:
        st.warning("No recordings available.")
