import re
import ast
import zipfile
import tempfile
from pathlib import Path

import requests
import streamlit as st
from groq import Groq


# ============================================================
# FIXFLOW AI - AGENTIC AUTONOMOUS BUG FIXING ASSISTANT
# API KEY IS ENTERED MANUALLY IN THE SIDEBAR
# ============================================================

st.set_page_config(
    page_title="FixFlow AI",
    page_icon="🔧",
    layout="wide"
)


# ============================================================
# LLM
# ============================================================

def call_llm(api_key, system_prompt, user_prompt):
    """Call Groq using the API key entered by the user."""

    if not api_key or not api_key.strip():
        return None, "Please enter your Groq API Key in the Setup section."

    try:
        client = Groq(api_key=api_key.strip())

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
        return None, f"Groq API Error: {str(e)}"


# ============================================================
# FILE INGESTION
# ============================================================

def extract_python_files_from_zip(uploaded_file):
    """Extract Python files safely from a ZIP upload."""
    files = {}

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = Path(temp_dir) / "project.zip"
        zip_path.write_bytes(uploaded_file.getbuffer())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():

                # Prevent path traversal
                if member.startswith("/") or ".." in Path(member).parts:
                    continue

                if member.endswith(".py"):
                    try:
                        files[member] = zip_ref.read(member).decode(
                            "utf-8", errors="ignore"
                        )
                    except Exception:
                        pass

    return files


# ============================================================
# GITHUB REPOSITORY INGESTION
# ============================================================

def parse_github_url(url):
    match = re.search(r"github\.com/([^/]+)/([^/#?]+)", url)
    if not match:
        return None, None

    return match.group(1), match.group(2).replace(".git", "")


def get_github_files(repo_url):
    """Read Python files from a public GitHub repository."""

    try:
        owner, repo = parse_github_url(repo_url)

        if not owner or not repo:
            return {}, "Invalid GitHub repository URL."

        api_url = (
            f"https://api.github.com/repos/{owner}/{repo}"
            f"/git/trees/HEAD?recursive=1"
        )

        response = requests.get(api_url, timeout=20)

        if response.status_code != 200:
            return {}, (
                "Unable to access this repository. "
                "Make sure the URL is correct and the repository is public."
            )

        tree = response.json().get("tree", [])

        python_files = [
            item for item in tree
            if item.get("type") == "blob"
            and item.get("path", "").endswith(".py")
        ][:30]

        files = {}

        for item in python_files:
            path = item["path"]

            raw_url = (
                f"https://raw.githubusercontent.com/"
                f"{owner}/{repo}/HEAD/{path}"
            )

            try:
                file_response = requests.get(raw_url, timeout=10)

                if file_response.status_code == 200:
                    files[path] = file_response.text

            except requests.RequestException:
                continue

        return files, None

    except Exception as e:
        return {}, str(e)


# ============================================================
# STATIC CODE ANALYSIS
# ============================================================

def analyze_python_syntax(code):
    try:
        ast.parse(code)
        return {"valid": True, "error": None}

    except SyntaxError as e:
        return {
            "valid": False,
            "error": f"Syntax Error at line {e.lineno}: {e.msg}"
        }


def get_project_summary(files):
    summary = []

    for filename, content in files.items():
        try:
            tree = ast.parse(content)

            functions = [
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]

            classes = [
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
            ]

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
    """Build code context for the LLM."""
    context = ""

    for filename, content in files.items():
        context += (
            f"\n\n### FILE: {filename}\n"
            f"```python\n{content[:12000]}\n```"
        )

    return context


# ============================================================
# AGENTS
# ============================================================

def detect_bugs_with_agent(api_key, files):

    system_prompt = """
You are an expert Python Bug Detection Agent.

Analyze the supplied code and identify only genuine issues supported by the code.

Check for:
- Syntax errors
- Runtime errors
- Logical bugs
- Incorrect variable usage
- Edge cases
- Potential exceptions

Return your answer in this format:

## Bugs Found

### Bug 1
- File:
- Line / Location:
- Problem:
- Severity: Low / Medium / High

## Root Cause Analysis

Explain why the problem happens.

## Recommended Fix

Explain the recommended solution.
"""

    user_prompt = (
        "Analyze the following Python project:\n"
        + build_code_context(files)
    )

    return call_llm(api_key, system_prompt, user_prompt)


def generate_fix_with_agent(api_key, files, bug_analysis):

    system_prompt = """
You are an expert Autonomous Code Fixing Agent.

Based on the original source code and bug analysis:

1. Fix only genuine problems.
2. Generate minimal and safe changes.
3. Preserve the original functionality.
4. Do not unnecessarily rewrite the entire project.

Return:

## Fix Summary

## Fixed Code

For every modified file use:

### filename.py

```python
corrected code here
```

## Why This Fix Works
"""

    user_prompt = f"""
SOURCE CODE:
{build_code_context(files)}

BUG ANALYSIS:
{bug_analysis}
"""

    return call_llm(api_key, system_prompt, user_prompt)


def review_fix(api_key, original_files, bug_analysis, fix_response):

    system_prompt = """
You are a senior software engineer acting as a Code Review Agent.

Review the proposed fix against the original bug analysis.

Evaluate:
1. Does the fix address the bug?
2. Could it introduce new problems?
3. Is the fix unnecessarily complex?
4. What is your confidence level?

Return:

## Review Result
## Confidence
## Potential Risks
## Final Recommendation
"""

    project_summary = "\n".join(
        f"- {name}: {len(code.splitlines())} lines"
        for name, code in original_files.items()
    )

    user_prompt = f"""
PROJECT FILES:
{project_summary}

BUG ANALYSIS:
{bug_analysis}

PROPOSED FIX:
{fix_response}
"""

    return call_llm(api_key, system_prompt, user_prompt)


# ============================================================
# STREAMLIT UI
# ============================================================

def main():

    st.title("🔧 FixFlow AI")
    st.subheader("Agentic Autonomous Bug Detection & Fixing Assistant")

    st.write(
        "Analyze Python code from manual input, uploaded files, "
        "or public GitHub repositories."
    )

    # --------------------------------------------------------
    # SIDEBAR SETUP
    # --------------------------------------------------------

    with st.sidebar:

        st.header("⚙️ Setup")

        # Manual API key entry
        api_key = st.text_input(
            "Groq API Key",
            type="password",
            placeholder="Enter your Groq API key",
            help="Your key is used only for the current session."
        )

        if api_key:
            st.success("API key entered ✓")
        else:
            st.caption("Enter your API key to run the AI agents.")

        st.divider()

        st.header("📥 Input Source")

        input_method = st.radio(
            "Choose your source:",
            [
                "✍️ Manual Code",
                "📁 Upload Files",
                "🔗 GitHub Repository",
            ]
        )

        st.divider()

        st.markdown("""
### 🤖 Agent Workflow

1. 📥 Code Ingestion
2. 🔍 Static Analysis
3. 🐛 Bug Detection
4. 🧠 Root Cause Analysis
5. 🔧 Fix Generation
6. 👨‍💻 Code Review
""")

    files = {}

    # --------------------------------------------------------
    # MANUAL CODE
    # --------------------------------------------------------

    if input_method == "✍️ Manual Code":

        code = st.text_area(
            "Paste your Python code here:",
            height=400,
            placeholder="def example():\n    print('Hello')"
        )

        filename = st.text_input(
            "Filename",
            value="main.py"
        )

        if code.strip():
            files[filename] = code

    # --------------------------------------------------------
    # FILE UPLOAD
    # --------------------------------------------------------

    elif input_method == "📁 Upload Files":

        uploaded_files = st.file_uploader(
            "Upload Python files or a ZIP project",
            type=["py", "zip"],
            accept_multiple_files=True
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:

                if uploaded_file.name.endswith(".py"):
                    files[uploaded_file.name] = (
                        uploaded_file.getvalue().decode(
                            "utf-8", errors="ignore"
                        )
                    )

                elif uploaded_file.name.endswith(".zip"):
                    try:
                        files.update(
                            extract_python_files_from_zip(uploaded_file)
                        )
                    except Exception as e:
                        st.error(f"Could not extract ZIP file: {e}")

    # --------------------------------------------------------
    # GITHUB REPOSITORY
    # --------------------------------------------------------

    elif input_method == "🔗 GitHub Repository":

        repo_url = st.text_input(
            "Enter a public GitHub repository URL:",
            placeholder="https://github.com/username/repository"
        )

        if st.button("📥 Load Repository"):

            if not repo_url:
                st.warning("Please enter a GitHub repository URL.")

            else:
                with st.spinner(
                    "Repository Agent is reading the codebase..."
                ):
                    loaded_files, error = get_github_files(repo_url)

                    if error:
                        st.error(error)

                    elif loaded_files:
                        st.session_state["github_files"] = loaded_files
                        st.success(
                            f"Loaded {len(loaded_files)} Python files!"
                        )
                    else:
                        st.warning(
                            "No Python files were found in this repository."
                        )

        if "github_files" in st.session_state:
            files = st.session_state["github_files"]

    # --------------------------------------------------------
    # PROJECT ANALYSIS
    # --------------------------------------------------------

    if not files:
        st.info(
            "👆 Select an input source and provide Python code "
            "to start the analysis."
        )
        return

    st.success(f"📂 {len(files)} Python file(s) ready for analysis")

    with st.expander("📁 View Project Structure"):

        for item in get_project_summary(files):

            st.markdown(f"**📄 {item['file']}**")

            st.caption(
                f"{item['lines']} lines | "
                f"Functions: {len(item['functions'])} | "
                f"Classes: {len(item['classes'])}"
            )

    # --------------------------------------------------------
    # STATIC ANALYSIS
    # --------------------------------------------------------

    st.divider()
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

    # --------------------------------------------------------
    # RUN AGENTS
    # --------------------------------------------------------

    st.divider()

    if st.button(
        "🚀 Start Autonomous Bug Analysis",
        type="primary",
        use_container_width=True
    ):

        if not api_key or not api_key.strip():
            st.error(
                "🔑 Please enter your Groq API Key in the Setup section "
                "before starting the analysis."
            )
            return

        with st.status(
            "Agents are analyzing your code...",
            expanded=True
        ) as status:

            st.write(
                "🔍 **Bug Detection Agent:** Analyzing codebase..."
            )

            bug_analysis, error = detect_bugs_with_agent(
                api_key, files
            )

            if error:
                status.update(
                    label="❌ Agent execution failed",
                    state="error"
                )
                st.error(error)
                return

            st.write(
                "🔧 **Fix Generation Agent:** Creating proposed fix..."
            )

            fix_response, error = generate_fix_with_agent(
                api_key, files, bug_analysis
            )

            if error:
                status.update(
                    label="❌ Fix generation failed",
                    state="error"
                )
                st.error(error)
                return

            st.write(
                "👨‍💻 **Review Agent:** Reviewing proposed solution..."
            )

            review_response, error = review_fix(
                api_key,
                files,
                bug_analysis,
                fix_response
            )

            if error:
                review_response = (
                    f"Review Agent could not complete: {error}"
                )

            status.update(
                label="✅ Agent workflow completed!",
                state="complete",
                expanded=False
            )

        # ----------------------------------------------------
        # RESULTS
        # ----------------------------------------------------

        tab1, tab2, tab3 = st.tabs([
            "🐛 Bugs Found",
            "🔧 Proposed Fix",
            "👨‍💻 Code Review"
        ])

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
            label="📥 Download Bug Fix Report",
            data=report,
            file_name="fixflow_bug_report.txt",
            mime="text/plain"
        )


if __name__ == "__main__":
    main()
