"""Reusable Streamlit UI components."""

import streamlit as st


def render_chat_messages(messages: list[dict]) -> None:
    """Render conversation history from session_state.messages format."""
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
