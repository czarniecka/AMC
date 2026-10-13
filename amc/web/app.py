"""Browser interface for local comment classification."""

import os
import time
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

from amc.classification.classifier import classify

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
st.set_page_config(page_title="AMC comment analysis", page_icon="💬")
st.title("Comment analysis")
st.caption("Local AI classification · two labels · human review required")
model = st.selectbox(
    "Model", list(dict.fromkeys([os.getenv("OLLAMA_MODEL", "qwen3:8b"), "qwen3:8b", "qwen3:4b"]))
)
with st.form("classify"):
    comment = st.text_area("Polish or English comment", height=180)
    submitted = st.form_submit_button("Classify", type="primary")
if submitted:
    if not comment.strip():
        st.warning("Enter a comment first.")
    else:
        try:
            start = time.perf_counter()
            with st.spinner("Classifying… First use may take longer."):
                labels = classify(comment.strip(), model)
            left, right = st.columns(2)
            left.metric("Relevance", labels["relevance"])
            right.metric("Impact", labels["impact"])
            st.caption(f"Completed in {time.perf_counter() - start:.1f} seconds.")
        except requests.RequestException:
            st.error("Cannot complete the Ollama request. Check the service and installed model.")
        except (ValueError, KeyError, TypeError):
            st.error("Invalid model response. Retry or classify this comment manually.")
st.info("Predictions are exploratory and are not automatically saved to the research dataset.")
