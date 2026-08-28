import os
import re
import ast
import zipfile
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

st.set_page_config(page_title="FixFlow AI", page_icon="🔧", layout="wide")
SUPPORTED_EXTENSIONS = {".py"}


@st.cache_resource
def get_llm_client():
    api_key = os.getenv("GROQ_API_KEY")
    return Groq(api_key=api_key) if api_key else None


def call_llm(system_prompt, user_prompt):
    client = get_llm_client()
    if client is None:
        return None, "GROQ_API_KEY not found. Add it to your .env file."

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=4000,
        )
        return response.choices[0].message.content, None
    except Exception as e:
        return None, str(e)


def extract_python_files_from_zip(uploaded_file):
    files = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "project.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                if member.startswith("/") or ".." in Path(member).parts:
                    continue
                if member.endswith(".py"):
                    try:
                        files[member] = zip_ref.read(member).decode(
                            "utf-8", errors="ignore"
                        )
                    except Exception:
                        continue
    return files


def parse_github_url(url):
    match = re.search(r"github\.com/([^/]+)/([^/#?]+)", url)
    if not match:
        return None, None
    return match.group(1), match.group(2).replace(".git", "")


def get_github_files(repo_url):
    import requests

    try:
        owner, repo = parse_github_url(repo_url)
        if not owner or not repo:
            return {}, "Invalid GitHub repository URL."

        api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        response = requests.get(api_url, timeout=20)

        if response.status_code != 200:
            return {}, "Unable to access repository. Make sure it is public."

        tree = response.json().get("tree", [])
        python_files = [
            item for item in tree
            if item.get("type") == "blob" and item.get("path", "").endswith(".py")
        ][:30]

        files = {}
        for item in python_files:
            path = item["path"]
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"
            try:
                file_response = requests.get(raw_url, timeout=10)
                if file_response.status_code == 200:
                    files[path] = file_response.text
            except Exception:
                continue

        return files, None
    except Exception as e:
        return {}, str(e)


def analyze_python_syntax(code):
    try:
        ast.parse(code)
        return {"valid": True, "error": None}
    except SyntaxError as e:
        return {
            "valid": False,
            "error": f"Syntax Error at line {e.lineno}: {e.msg}",
        }


def get_project_summary(files):
    summary = []
    for filename, content in files.items():
        try:
            tree = ast.parse(content)
            functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        except Exception:
            functions, classes = [], []

        summary.append({
            "file": filename,
            "lines": len(content.splitlines()),
            "functions": functions,
            "classes": classes,
        })
    return summary


def build_code_context(files):
    context = ""
    for filename, content in files.items():
        context += f"\n\n### FILE: {filename}\n```python\n{content[:12000]}\n```"
    return context


def detect_bugs_with_agent(files):
    system_prompt = """You are an expert Python Bug Detection Agent.
Analyze the supplied code for syntax errors, runtime errors, logical bugs,
incorrect variable usage, edge cases, and potential exceptions. Do not invent bugs.

Return:
## Bugs Found
### Bug 1
- File:
- Line / Location:
- Problem:
- Severity:

## Root Cause Analysis

## Recommended Fix
"""
    return call_llm(system_prompt, f"Analyze this Python project:\n{build_code_context(files)}")


def generate_fix_with_agent(files, bug_analysis):
    system_prompt = """You are an expert Autonomous Code Fixing Agent.
Based on the source code and bug analysis, generate minimal and safe fixes.
Preserve original functionality and do not unnecessarily rewrite the project.

Return:
## Fix Summary
## Fixed Code
For every modified file use a heading with the filename followed by a Python code block.
## Why This Fix Works
"""
    prompt = f"""SOURCE CODE:
{build_code_context(files)}

BUG ANALYSIS:
{bug_analysis}
"""
    return call_llm(system_prompt, prompt)


def review_fix(original_files, bug_analysis, fix_response):
    system_prompt = """You are a senior software engineer acting as a Code Review Agent.
Review whether the proposed fix addresses the identified bug and whether it may
introduce new problems.

Return:
## Review Result
## Confidence
## Potential Risks
## Final Recommendation
"""
    summary = "\n".join(
        f"- {name}: {len(code.splitlines())} lines"
        for name, code in original_files.items()
    )
    prompt = f"""PROJECT FILES:
{summary}

BUG ANALYSIS:
{bug_analysis}

PROPOSED FIX:
{fix_response}
"""
    return call_llm(system_prompt, prompt)


def main():
    st.title("🔧 FixFlow AI")
    st.subheader("Agentic Autonomous Bug Detection & Fixing Assistant")
    st.write(
        "Analyze Python code from manual input, uploaded files, or public GitHub repositories."
    )

    with st.sidebar:
        st.header("⚙️ Input Source")
        input_method = st.radio(
            "Choose your source:",
            ["✍️ Manual Code", "📁 Upload Files", "🔗 GitHub Repository"],
        )
        st.markdown("""### 🤖 Agent Workflow
1. 📥 Code Ingestion
2. 🔍 Static Analysis
3. 🐛 Bug Detection Agent
4. 🧠 Root Cause Analysis
5. 🔧 Fix Generation Agent
6. 👨‍💻 Review Agent
""")

    files = {}

    if input_method == "✍️ Manual Code":
        code = st.text_area("Paste your Python code here:", height=400)
        filename = st.text_input("Filename", value="main.py")
        if code.strip():
            files[filename] = code

    elif input_method == "📁 Upload Files":
        uploaded_files = st.file_uploader(
            "Upload Python files or a ZIP project",
            type=["py", "zip"],
            accept_multiple_files=True,
        )
        if uploaded_files:
            for uploaded_file in uploaded_files:
                if uploaded_file.name.endswith(".py"):
                    files[uploaded_file.name] = uploaded_file.getvalue().decode(
                        "utf-8", errors="ignore"
                    )
                elif uploaded_file.name.endswith(".zip"):
                    try:
                        files.update(extract_python_files_from_zip(uploaded_file))
                    except Exception as e:
                        st.error(f"Could not extract ZIP: {e}")

    else:
        repo_url = st.text_input(
            "Enter a public GitHub repository URL:",
            placeholder="https://github.com/username/repository",
        )
        if st.button("📥 Load Repository") and repo_url:
            with st.spinner("Repository Agent is reading the codebase..."):
                loaded_files, error = get_github_files(repo_url)
                if error:
                    st.error(error)
                elif loaded_files:
                    st.session_state["github_files"] = loaded_files
                    st.success(f"Loaded {len(loaded_files)} Python files!")

        if "github_files" in st.session_state:
            files = st.session_state["github_files"]

    if not files:
        st.info("👆 Select an input source and provide Python code to start.")
        return

    st.success(f"📂 {len(files)} Python file(s) ready for analysis")

    with st.expander("📁 View Project Structure"):
        for item in get_project_summary(files):
            st.markdown(f"**📄 {item['file']}**")
            st.caption(
                f"{item['lines']} lines | Functions: {len(item['functions'])} | "
                f"Classes: {len(item['classes'])}"
            )

    st.header("🔍 Static Code Analysis")
    syntax_issues = []
    for filename, code in files.items():
        result = analyze_python_syntax(code)
        if not result["valid"]:
            syntax_issues.append((filename, result["error"]))

    if syntax_issues:
        for filename, error in syntax_issues:
            st.error(f"**{filename}** → {error}")
    else:
        st.success("✅ No Python syntax errors detected!")

    if st.button("🚀 Start Autonomous Bug Analysis", type="primary", use_container_width=True):
        with st.status("Agents are analyzing your code...", expanded=True) as status:
            st.write("🔍 **Bug Detection Agent:** Analyzing codebase...")
            bug_analysis, error = detect_bugs_with_agent(files)
            if error:
                status.update(label="❌ Agent execution failed", state="error")
                st.error(error)
                return

            st.write("🔧 **Fix Generation Agent:** Creating proposed fix...")
            fix_response, error = generate_fix_with_agent(files, bug_analysis)
            if error:
                status.update(label="❌ Fix generation failed", state="error")
                st.error(error)
                return

            st.write("👨‍💻 **Review Agent:** Reviewing solution...")
            review_response, error = review_fix(files, bug_analysis, fix_response)
            if error:
                review_response = f"Review Agent could not complete: {error}"

            status.update(label="✅ Agent workflow completed!", state="complete")

        tab1, tab2, tab3 = st.tabs(["🐛 Bugs Found", "🔧 Proposed Fix", "👨‍💻 Code Review"])
        with tab1:
            st.markdown(bug_analysis)
        with tab2:
            st.markdown(fix_response)
        with tab3:
            st.markdown(review_response)

        report = f"""FIXFLOW AI - BUG FIXING REPORT

================ BUG ANALYSIS ================
{bug_analysis}

================ PROPOSED FIX ================
{fix_response}

================ CODE REVIEW ================
{review_response}
"""
        st.download_button(
            "📥 Download Bug Fix Report",
            report,
            "fixflow_bug_report.txt",
            "text/plain",
        )


if __name__ == "__main__":
    main()
