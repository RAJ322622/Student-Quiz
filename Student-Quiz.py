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

    # Create 'users' table if it doesn't exist
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT,
                        role TEXT DEFAULT 'student')''')

    # ✅ Add email column if it doesn't exist
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if "email" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()

    # Create other tables
    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                        username TEXT PRIMARY KEY,
                        change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                        username TEXT PRIMARY KEY,
                        attempt_count INTEGER DEFAULT 0)''')

    return conn


def add_email_column_if_not_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if "email" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()
    conn.close()




def add_email_column_if_not_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if "email" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()
    conn.close()


# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Register user
def register_user(username, password, role, email):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     (username, hash_password(password), role))
        conn.commit()
        st.success("Registration successful! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    finally:
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

# Active student tracking
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

# Dummy question bank
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

# Video processor
class VideoProcessor(VideoTransformerBase):
    def recv(self, frame):
        return frame

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
            conn = get_db_connection()
            try:
                conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                         (username, password_hashed, role, email))
                conn.commit()
                st.success("Registration successful! Please login.")
            except sqlite3.IntegrityError:
                st.error("Username or Email already exists!")
            conn.close()

        else:
            st.error("Incorrect OTP!")


elif choice == "Login":
    st.subheader("Login")

    # ---------- Login Form ----------
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login successful!")
        else:
            st.error("Invalid username or password.")

    # ---------- Forgot Password ----------
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

    # ---------- Reset Password ----------
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

                    # Clear session
                    del st.session_state['reset_otp']
                    del st.session_state['reset_email']
                    del st.session_state['reset_user']
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

                time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                time_limit = 25 * 60  # 25 minutes
                time_left = time_limit - time_elapsed

                if time_left <= 0:
                    st.warning("⏰ Time is up! Auto-submitting your quiz.")
                    st.session_state.auto_submit = True
                else:
                    mins, secs = divmod(time_left, 60)
                    st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")

                answers = {}

                if not st.session_state.quiz_submitted and not st.session_state.camera_active:
                    add_active_student(username)
                    st.session_state.camera_active = True

                if st.session_state.camera_active and not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_streamer(
                        key="camera",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={"video": True, "audio": False},
                        video_processor_factory=VideoProcessor,
                    )

                for idx, question in enumerate(QUESTIONS):
                    st.markdown(f"**Q{idx+1}:** {question['question']}")
                    ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
                    answers[question['question']] = ans

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

                        # Append to professor's CSV
                                                # Append to professor's CSV
                        if os.path.exists(PROF_CSV_FILE):
                            prof_df = pd.read_csv(PROF_CSV_FILE)
                            prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                        else:
                            prof_df = new_row
                        prof_df.to_csv(PROF_CSV_FILE, index=False)

                        # Save to student section-wise CSV
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
                        conn.close()

                        # Send results via email
                        conn = get_db_connection()
                        email_result = conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                        conn.close()
                        if email_result:
                            student_email = email_result[0]
                            try:
                                msg = EmailMessage()
                                msg.set_content(f"Dear {username},\n\nYou have successfully submitted your quiz.\nScore: {score}/{len(QUESTIONS)}\nTime Taken: {time_taken} seconds\n\nThank you for participating.")
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


                        # Send result via email
                        email_conn = get_db_connection()
                        email_cur = email_conn.cursor()
                        email_cur.execute("SELECT email FROM users WHERE username = ?", (username,))
                        email_record = email_cur.fetchone()
                        email_conn.close()

                        if email_record and email_record[0]:
                            try:
                                result_msg = EmailMessage()
                                result_msg.set_content(f"Hello {username},\n\nYou scored {score}/{len(QUESTIONS)} in the Secure Quiz.\n\nThank you!")
                                result_msg['Subject'] = "Your Secure Quiz Result"
                                result_msg['From'] = "rajkumar.k0322@gmail.com"
                                result_msg['To'] = email_record[0]

                                server = smtplib.SMTP('smtp.gmail.com', 587)
                                server.starttls()
                                server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")  # App password
                                server.send_message(result_msg)
                                server.quit()

                                st.success("Quiz result has been emailed to you.")
                            except Exception as e:
                                st.warning(f"Result email failed: {e}")

                        # Cleanup session & camera
                        st.success(f"✅ Quiz submitted successfully! You scored {score} out of {len(QUESTIONS)}.")
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
        if not st.session_state.get('prof_verified', False):
            prof_id = st.text_input("Professor ID", key="prof_id_login")
            prof_pass = st.text_input("Professor Password", type="password", key="prof_pass_login")
            
            if st.button("Login as Professor"):
                conn = get_db_connection()
                cursor = conn.execute("SELECT password, role, email FROM users WHERE username = ?", (prof_id,))
                prof_data = cursor.fetchone()
                conn.close()
                
                if prof_data and prof_data[1] == "professor" and prof_data[0] == hash_password(prof_pass):
                    st.session_state.prof_verified = True
                    st.session_state.username = prof_id
                    st.session_state.role = "professor"
                    st.success(f"Login successful! Welcome Professor {prof_id}")
                    
                    # Send login notification email
                    try:
                        msg = EmailMessage()
                        msg.set_content(f"Professor login detected:\n\nUsername: {prof_id}\nTime: {datetime.now()}")
                        msg['Subject'] = "Professor Login Notification"
                        msg['From'] = "rajkumar.k0322@gmail.com"
                        msg['To'] = prof_data[2]  # Professor's email

                        server = smtplib.SMTP('smtp.gmail.com', 587)
                        server.starttls()
                        server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
                        server.send_message(msg)
                        server.quit()
                    except Exception as e:
                        st.error(f"Login notification failed: {e}")
                    
                    # Create professor-specific CSV file path
                    PROF_CSV_FILE = f"prof_{prof_id}_results.csv"
                    st.session_state.prof_csv_file = PROF_CSV_FILE
                else:
                    st.error("Invalid Professor ID or password")
        else:
            st.success(f"Welcome Professor {st.session_state.username}!")
            
            # Professor dashboard after login
            PROF_CSV_FILE = st.session_state.get('prof_csv_file', "prof_quiz_results.csv")
            if os.path.exists(PROF_CSV_FILE):
                with open(PROF_CSV_FILE, "rb") as file:
                    st.download_button("\U0001F4E5 Download Results CSV", file, 
                                    f"{st.session_state.username}_quiz_results.csv", 
                                    mime="text/csv")
                
                # Show results preview
                st.subheader("Your Quiz Results Preview")
                prof_df = pd.read_csv(PROF_CSV_FILE)
                st.dataframe(prof_df)
            else:
                st.warning("No results available yet.")
            
            if st.button("Logout Professor"):
                st.session_state.prof_verified = False
                st.session_state.username = ""
                st.session_state.prof_csv_file = ""
                st.experimental_rerun()
    
    with tab2:  # Registration tab
        st.subheader("Professor Registration")
        st.warning("Professor registration requires institutional verification.")
        
        # Professor details collection
        full_name = st.text_input("Full Name")
        designation = st.text_input("Designation")
        department = st.selectbox("Department", ["CSE", "ISE", "ECE", "EEE", "MECH", "CIVIL"])
        institutional_email = st.text_input("Institutional Email", help="Must be your college email")
        
        if st.button("Request Professor Account"):
            if full_name and designation and department and institutional_email:
                # Generate professor credentials
                prof_id = f"RRCE-{random.randint(10000, 99999)}"
                prof_password = str(random.randint(100000, 999999))
                
                # Register professor
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                             (prof_id, hash_password(prof_password), "professor", institutional_email))
                    conn.commit()
                    
                    # Send credentials via email
                    try:
                        msg = EmailMessage()
                        msg.set_content(f"""Dear Professor {full_name},

Your professor account has been created with the following credentials:

Professor ID: {prof_id}
Password: {prof_password}

Please keep these credentials secure and do not share with students.

You can now login to the Secure Quiz App professor panel.

Best regards,
Secure Quiz App Team""")
                        msg['Subject'] = "Your Professor Account Credentials"
                        msg['From'] = "rajkumar.k0322@gmail.com"
                        msg['To'] = institutional_email

                        server = smtplib.SMTP('smtp.gmail.com', 587)
                        server.starttls()
                        server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
                        server.send_message(msg)
                        server.quit()
                        
                        st.success("Professor account created! Your credentials have been sent to your institutional email.")
                    except Exception as e:
                        st.error(f"Account created but failed to send email: {e}")
                except sqlite3.IntegrityError:
                    st.error("Professor with this email already exists!")
                finally:
                    conn.close()
            else:
                st.error("Please fill all the details")
elif choice == "Professor Monitoring Panel":
    if not st.session_state.prof_verified:
        st.warning("Professor access only. Please login via 'Professor Panel' to verify.")
    else:
        st_autorefresh(interval=10 * 1000, key="monitor_refresh")
        st.header("\U0001F4E1 Live Student Monitoring")
        st.info("Students currently taking the quiz will appear here.")
        live_stream_ids = get_live_students()
        if not live_stream_ids:
            st.write("No active students currently taking the quiz.")
        else:
            for student_id in live_stream_ids:
                st.subheader(f"Live Feed from: {student_id}")
                st.warning("Note: Real-time video streaming from remote users is not supported on Streamlit Community Cloud.")
                st.write(f"\U0001F464 {student_id} is currently taking the quiz.")

elif choice == "View Recorded Video":
    st.subheader("Recorded Quiz Videos")
    video_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
    if video_files:
        selected_video = st.selectbox("Select a recorded video:", video_files)
        st.video(os.path.join(RECORDING_DIR, selected_video))
    else:
        st.warning("No recorded videos found.")
