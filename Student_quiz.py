# student_quiz_app/app.py

import streamlit as st
from auth import login_page, signup_page, check_auth
from quiz import run_quiz
from leaderboard import show_leaderboard
from admin_dashboard import show_admin_dashboard

st.set_page_config(page_title="Student Quiz", layout="centered")

if "page" not in st.session_state:
    st.session_state.page = "login"

if st.session_state.page == "signup":
    signup_page()
elif st.session_state.page == "login":
    login_page()
elif st.session_state.page == "quiz":
    run_quiz()
elif st.session_state.page == "leaderboard":
    show_leaderboard()
elif st.session_state.page == "admin":
    show_admin_dashboard()

# End of app.py
