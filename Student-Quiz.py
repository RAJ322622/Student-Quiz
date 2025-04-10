import streamlit as st
import pandas as pd
import cv2
import os
import uuid
from gtts import gTTS
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
from datetime import datetime, timedelta

# ---- Dummy user auth (replace with real login logic) ----
users = {
    "student1": {"password": "pass123", "role": "student", "attempts": 0, "password_changes": 0, "section": "A", "usn": "S001"},
    "professor1": {"password": "admin123", "role": "professor"}
}

# ---- Webcam ----
class VideoTransformer(VideoTransformerBase):
    def transform(self, frame):
        return frame

# ---- Audio Quiz Question ----
def play_audio(text):
    tts = gTTS(text=text, lang='en')
    filename = "temp.mp3"
    tts.save(filename)
    st.audio(filename, format='audio/mp3')

# ---- Quiz Questions ----
questions = [
    {"q": "What is 2 + 2?", "options": ["3", "4", "5"], "answer": "4"},
    {"q": "Capital of France?", "options": ["Berlin", "London", "Paris"], "answer": "Paris"},
]

# ---- Login UI ----
def login():
    st.title("Secure Quiz App")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username in users and users[username]["password"] == password:
            st.session_state["user"] = username
            st.session_state["role"] = users[username]["role"]
            return True
        else:
            st.error("Invalid credentials")
    return False

# ---- Student Quiz ----
def student_quiz():
    user = users[st.session_state["user"]]
    if user["attempts"] >= 2:
        st.warning("You have reached the maximum number of attempts.")
        return

    section = user["section"]
    usn = user["usn"]
    st.write(f"**Section:** {section}, **USN:** {usn}")
    st.subheader("Webcam Monitoring (Stay Visible)")
    webrtc_ctx = webrtc_streamer(key="student", video_transformer_factory=VideoTransformer)

    if not webrtc_ctx.state.playing:
        st.warning("Please turn on your webcam to continue.")
        return

    st.subheader("Quiz Timer")
    if "start_time" not in st.session_state:
        st.session_state["start_time"] = datetime.now()
    time_left = timedelta(minutes=25) - (datetime.now() - st.session_state["start_time"])
    if time_left.total_seconds() <= 0:
        st.error("Time is up!")
        return
    st.success(f"Time Left: {str(time_left).split('.')[0]}")

    st.subheader("Quiz Questions")
    answers = []
    for i, q in enumerate(questions):
        st.write(f"Q{i+1}: {q['q']}")
        play_audio(q['q'])  # Play audio
        ans = st.radio("Select answer:", q["options"], key=f"q{i}")
        answers.append(ans)

    if st.button("Submit Quiz"):
        if not webrtc_ctx.state.playing:
            st.error("Webcam must be ON to submit the quiz.")
            return

        score = sum([1 for i, q in enumerate(questions) if answers[i] == q["answer"]])
        user["attempts"] += 1
        filename = f"results_section_{section}.csv"
        data = {
            "usn": usn,
            "section": section,
            "attempt": user["attempts"],
            "score": score,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if os.path.exists(filename):
            df = pd.read_csv(filename)
            df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
        else:
            df = pd.DataFrame([data])
        df.to_csv(filename, index=False)
        st.success(f"Quiz submitted successfully! Your score: {score}/ {len(questions)}")

# ---- Professor Panel ----
def professor_panel():
    st.title("Professor Dashboard")
    uploaded = st.file_uploader("Upload Section CSV to View Results", type="csv")
    if uploaded:
        df = pd.read_csv(uploaded)
        st.dataframe(df)

# ---- Password Change ----
def change_password():
    user = users[st.session_state["user"]]
    if user["password_changes"] >= 2:
        st.warning("Password change limit reached.")
        return
    st.subheader("Change Password")
    new_pass = st.text_input("New Password", type="password")
    if st.button("Update Password"):
        users[st.session_state["user"]]["password"] = new_pass
        users[st.session_state["user"]]["password_changes"] += 1
        st.success("Password updated successfully!")

# ---- Main App ----
def main():
    if "user" not in st.session_state:
        if not login():
            return

    st.sidebar.write(f"Logged in as: {st.session_state['user']} ({st.session_state['role']})")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()

    if st.session_state["role"] == "student":
        student_quiz()
        change_password()
    elif st.session_state["role"] == "professor":
        professor_panel()

main()
