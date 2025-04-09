import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pyttsx3
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
import av
from datetime import datetime
import imageio
from pydub import AudioSegment

VIDEO_DIR = "videos"
RECORDING_DIR = "recordings"
CSV_FILE = "quiz_results.csv"

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

# DB Setup
def get_db_connection():
    conn = sqlite3.connect("quiz_app.db")
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
        st.success("Registered successfully! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists.")
    conn.close()

def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and user[0] == hash_password(password)

QUESTIONS = [
    {"question": "🔤 Which data type is used to store a single character in C?", "options": ["char", "int", "float", "double"], "answer": "char"},
    {"question": "🔢 What is the output of 5 / 2 in C if both operands are integers?", "options": ["2.5", "2", "3", "Error"], "answer": "2"},
]

# Text-to-Speech using pyttsx3
def generate_audio(text, filename):
    if not os.path.exists(filename):
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.save_to_file(text, filename)
        engine.runAndWait()

# Video creator using imageio
def create_video(question_text, filename, audio_file):
    video_path = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(video_path):
        return video_path

    width, height = 640, 480
    bg_color = (255, 223, 186)
    text_color = (0, 0, 0)
    font_size = 24
    duration_sec = 5
    fps = 10
    total_frames = duration_sec * fps

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    images = []
    for _ in range(total_frames):
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)
        text_w, text_h = draw.textsize(question_text, font=font)
        draw.text(((width - text_w) / 2, (height - text_h) / 2), question_text, fill=text_color, font=font)
        images.append(np.array(img))

    gif_path = video_path.replace(".mp4", ".gif")
    imageio.mimsave(gif_path, images, fps=fps)

    audio = AudioSegment.from_file(audio_file)
    audio.export(video_path.replace(".mp4", ".wav"), format="wav")

    reader = imageio.get_reader(gif_path)
    writer = imageio.get_writer(video_path, fps=fps)
    for frame in reader:
        writer.append_data(frame)
    writer.close()

    return video_path

class VideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.container = av.open(os.path.join(RECORDING_DIR, "quiz_recording.mp4"), mode="w")
        self.stream = self.container.add_stream("h264", rate=24)
        self.stream.width = 640
        self.stream.height = 480
        self.stream.pix_fmt = "yuv420p"

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        packet = self.stream.encode(frame)
        if packet:
            self.container.mux(packet)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        self.container.close()

st.title("🎥 Interactive Video Quiz 🎬")

menu = ["Register", "Login", "Take Quiz", "View Recorded Video"]
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
            st.error("Invalid credentials")

elif choice == "Take Quiz":
    if not st.session_state["logged_in"]:
        st.warning("Please login first!")
    else:
        username = st.session_state["username"]
        score = 0
        start_time = time.time()
        answers = {}

        st.subheader("📷 Live Monitoring")
        webrtc_streamer(
            key="monitor",
            mode=WebRtcMode.SENDRECV,
            media_stream_constraints={"video": True, "audio": False},
            video_processor_factory=VideoProcessor,
        )

        for idx, q in enumerate(QUESTIONS):
            question_text = q["question"]
            audio_file = os.path.join(VIDEO_DIR, f"q{idx}.wav")
            video_file = f"q{idx}.mp4"

            generate_audio(question_text, audio_file)
            video_path = create_video(question_text, video_file, audio_file)

            st.video(video_path)
            selected = st.radio(f"Question {idx+1}", q["options"], key=f"q{idx}")
            answers[q["question"]] = selected

        if st.button("Submit Quiz"):
            for q in QUESTIONS:
                if answers.get(q["question"]) == q["answer"]:
                    score += 1
            duration = round(time.time() - start_time, 2)
            st.success(f"Score: {score}")
            st.info(f"Time Taken: {duration} sec")

            df = pd.DataFrame([[username, score, duration, datetime.now()]],
                              columns=["Username", "Score", "Time_Taken", "Timestamp"])
            try:
                existing = pd.read_csv(CSV_FILE)
                final = pd.concat([existing, df], ignore_index=True)
            except:
                final = df
            final.to_csv(CSV_FILE, index=False)
            st.success("Result saved!")

elif choice == "View Recorded Video":
    st.subheader("🎞️ Recorded Video")
    files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
    if files:
        selected = st.selectbox("Select video", files)
        st.video(os.path.join(RECORDING_DIR, selected))
    else:
        st.info("No recorded videos found.")
