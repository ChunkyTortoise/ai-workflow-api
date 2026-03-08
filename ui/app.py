"""Streamlit UI for AI Workflow API."""
from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="AI Workflow API",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ AI Workflow API")
st.caption("YAML-driven workflow automation with LLM orchestration and SSE streaming")

# Sidebar — API config
with st.sidebar:
    st.header("Configuration")
    api_url = st.text_input("API URL", value=API_BASE)
    api_key = st.text_input("API Key (optional)", type="password", placeholder="Leave empty if disabled")
    st.divider()
    st.caption("The /demo endpoint works without an API key or ANTHROPIC_API_KEY.")


def get_headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
    return h


# Main tabs
tab_demo, tab_workflows, tab_jobs = st.tabs(["🚀 Demo", "📋 Workflows", "⚙️ Jobs"])

with tab_demo:
    st.subheader("Quick Demo")
    st.info("Runs a mock workflow without any API keys. Perfect for evaluating the pipeline.")

    col1, col2 = st.columns([3, 1])
    with col1:
        demo_text = st.text_area(
            "Input text",
            value="Explain the benefits of YAML-driven workflow automation for enterprise teams.",
            height=100,
        )
    with col2:
        workflow_id = st.selectbox("Workflow", ["summarize", "classify", "extract"])

    if st.button("Run Demo", type="primary"):
        with st.spinner("Running workflow..."):
            try:
                resp = httpx.post(
                    f"{api_url}/demo",
                    json={"text": demo_text, "workflow_id": workflow_id},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    st.success("Workflow complete!")

                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Steps", len(data.get("steps_executed", [])))
                    col_b.metric("Tokens", data.get("tokens_used", 0))
                    col_c.metric("Demo Mode", "Yes" if data.get("demo_mode") else "No")

                    st.markdown("**Result:**")
                    st.info(data.get("result", "No result"))

                    with st.expander("Step details"):
                        for step in data.get("steps_log", []):
                            st.write(f"**{step['step']}** — {step['status']}")
                else:
                    st.error(f"API error: {resp.status_code} — {resp.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")
                st.caption(f"Make sure the API is running at {api_url}")

with tab_workflows:
    st.subheader("Available Workflows")

    if st.button("Refresh Workflows"):
        try:
            resp = httpx.get(f"{api_url}/api/v1/workflows", headers=get_headers(), timeout=5)
            if resp.status_code == 200:
                workflows: list[dict[str, Any]] = resp.json()
                if workflows:
                    for wf in workflows:
                        with st.expander(f"{wf.get('name', wf.get('id', 'Unknown'))}"):
                            st.json(wf)
                else:
                    st.info("No workflows found. Add YAML files to the workflows/ directory.")
            else:
                st.error(f"Error: {resp.status_code}")
        except Exception as e:
            st.error(f"Cannot connect to API: {e}")

with tab_jobs:
    st.subheader("Submit Job")

    job_workflow = st.text_input("Workflow ID", value="summarize")
    job_input = st.text_area("Job Input (JSON)", value='{"text": "Your input here"}', height=80)

    if st.button("Submit Job", type="primary"):
        try:
            input_data = json.loads(job_input)
            resp = httpx.post(
                f"{api_url}/api/v1/runs/{job_workflow}/execute",
                json={"data": input_data},
                headers=get_headers(),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                job: dict[str, Any] = resp.json()
                st.success(f"Job submitted: `{job.get('id', '???')}`")
                st.json(job)
            else:
                st.error(f"Error {resp.status_code}: {resp.text}")
        except json.JSONDecodeError:
            st.error("Invalid JSON in job input")
        except Exception as e:
            st.error(f"Error: {e}")
