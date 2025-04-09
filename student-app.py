import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import moviepy.editor as mp
from gtts import gTTS
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
import av
from datetime import datetime

# Ensure directories exist
VIDEO_DIR = "videos"
RECORDING_DIR = "recordings"
CSV_FILE = "quiz_results.csv"

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "username" not in st.session_state:
    st.session_state["username"] = ""

# Database connection
def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)''')
    return conn

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User registration
def register_user(username, password):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        st.success("Registration successful! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    conn.close()

# User authentication
def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and user[0] == hash_password(password)

# Quiz questions
QUESTIONS = [
    {"question": "Which data type is used to store a single character in C?", "options": ["char", "int", "float", "double"], "answer": "char"},
    {"question": "What is the output of 5 / 2 in C if both operands are integers?", "options": ["2.5", "2", "3", "Error"], "answer": "2"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
    {"question": "What is the format specifier for printing an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which operator is used for incrementing a variable by 1 in C?", "options": ["+", "++", "--", "="], "answer": "++"},
]

# Generate audio for questions
def generate_audio(question_text, filename):
    if not os.path.exists(filename):
        tts = gTTS(text=question_text, lang='en')
        tts.save(filename)

# Create video from image frames and audio
def create_video(question_text, filename, audio_file):
    video_path = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(video_path):
        return video_path

    width, height = 640, 480
    background_color = (255, 223, 186)
    text_color = (0, 0, 0)
    font_size = 24
    duration = 5
    fps = 10
    total_frames = duration * fps

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    frames = []
    for _ in range(total_frames):
        img = Image.new("RGB", (width, height), color=background_color)
        draw = ImageDraw.Draw(img)
        text_width, text_height = draw.textsize(question_text, font=font)
        text_x = (width - text_width) // 2
        text_y = (height - text_height) // 2
        draw.text((text_x, text_y), question_text, fill=text_color, font=font)
        frames.append(np.array(img))

    clip = mp.ImageSequenceClip(frames, fps=fps)
    audio_clip = mp.AudioFileClip(audio_file)
    final_clip = clip.set_audio(audio_clip).set_duration(audio_clip.duration)
    final_clip.write_videofile(video_path, codec='libx264', audio_codec='aac')

    return video_path

# Video Processor for recording webcam
class VideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.recording = True
        self.container = av.open(os.path.join(RECORDING_DIR, "quiz_recording.mp4"), mode="w", format="mp4")
        self.stream = self.container.add_stream("h264")

    def recv(self, frame):
        frame_bgr = frame.to_ndarray(format="bgr24")
        video_frame = av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")
        if self.recording:
            packet = self.stream.encode(video_frame)
            if packet:
                self.container.mux(packet)
        return video_frame

    def close(self):
        self.container.close()

# Streamlit UI
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
            st.error("Invalid credentials!")

elif choice == "Take Quiz":
    if not st.session_state["logged_in"]:
        st.warning("Please login first!")
    else:
        username = st.session_state["username"]
        score = 0
        start_time = time.time()
        answers = {}

        st.subheader("📷 Live Camera Monitoring Enabled")
        webrtc_streamer(
            key="camera",
            mode=WebRtcMode.SENDRECV,
            media_stream_constraints={"video": True, "audio": False},
            video_processor_factory=VideoProcessor,
        )

        for idx, question in enumerate(QUESTIONS):
            question_text = question["question"]
            audio_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp3")
            video_file = os.path.join(VIDEO_DIR, f"{username}_question_{idx}.mp4")

            generate_audio(question_text, audio_file)
            video_file = create_video(question_text, video_file, audio_file)

            st.video(video_file)
            selected_option = st.radio(f"Select your answer for Question {idx+1}", question["options"], key=f"q{idx}")
            answers[question_text] = selected_option

        if st.button("Submit Quiz"):
            for question in QUESTIONS:
                if answers.get(question["question"]) == question["answer"]:
                    score += 1

            time_taken = round(time.time() - start_time, 2)
            st.write(f"Your Score: {score}")
            st.write(f"Time Taken: {time_taken} seconds")

            df = pd.DataFrame([[username, score, time_taken, datetime.now()]], 
                              columns=["Username", "Score", "Time_Taken", "Timestamp"])
            try:
                existing_df = pd.read_csv(CSV_FILE)
                updated_df = pd.concat([existing_df, df], ignore_index=True)
            except FileNotFoundError:
                updated_df = df
            updated_df.to_csv(CSV_FILE, index=False)

            st.success("Quiz completed and saved!")

elif choice == "View Recorded Video":
    st.subheader("Recorded Quiz Videos")
    video_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
    if video_files:
        selected_video = st.selectbox("Select a recorded video:", video_files)
        st.video(os.path.join(RECORDING_DIR, selected_video))
    else:
        st.warning("No recorded videos found.")
