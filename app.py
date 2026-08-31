import re
import ast
import zipfile
import tempfile
import base64
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
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------
# BACKGROUND MEDIA CONFIG
# Drop a background video or GIF into an "assets" folder next
# to this script and point to it below. MP4 is recommended
# (much smaller file size, smoother playback than GIF).
# If neither file is found, an animated gradient is used
# automatically so the app still looks good out of the box.
# ------------------------------------------------------------
BG_VIDEO_PATH = "assets/bg.mp4"
BG_GIF_PATH = "assets/bg.gif"

# ------------------------------------------------------------
# DEMO LOGIN CREDENTIALS
# Replace this with real auth (DB / OAuth / etc.) for production.
# ------------------------------------------------------------
DEMO_USERS = {
    "admin": "admin123",
    "demo": "demo123",
}


# ============================================================
# BACKGROUND RENDERING (video / GIF / animated fallback)
# ============================================================

def _file_to_base64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def inject_background():
    """Render a full-screen looping video/GIF behind the app.
    Falls back to an animated gradient if no asset file exists."""

    if Path(BG_VIDEO_PATH).exists():
        video_b64 = _file_to_base64(BG_VIDEO_PATH)
        st.markdown(
            f"""
            <style>
            .stApp {{ background: transparent; }}
            #bg-media {{
                position: fixed;
                top: 0; left: 0;
                width: 100vw; height: 100vh;
                object-fit: cover;
                z-index: -2;
            }}
            #bg-overlay {{
                position: fixed;
                top: 0; left: 0;
                width: 100vw; height: 100vh;
                background: rgba(10, 10, 20, 0.55);
                z-index: -1;
            }}
            </style>
            <video autoplay muted loop playsinline id="bg-media">
                <source src="data:video/mp4;base64,{video_b64}" type="video/mp4">
            </video>
            <div id="bg-overlay"></div>
            """,
            unsafe_allow_html=True,
        )

    elif Path(BG_GIF_PATH).exists():
        gif_b64 = _file_to_base64(BG_GIF_PATH)
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image:
                    linear-gradient(rgba(10,10,20,0.55), rgba(10,10,20,0.55)),
                    url("data:image/gif;base64,{gif_b64}");
                background-size: cover;
                background-position: center;
                background-attachment: fixed;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    else:
        # No local asset found yet -> animated gradient fallback
        st.markdown(
            """
            <style>
            .stApp {
                background: linear-gradient(-45deg, #0f2027, #1c2b3a, #2c5364, #16222a);
                background-size: 400% 400%;
                animation: gradientShift 12s ease infinite;
            }
            @keyframes gradientShift {
                0%   { background-position: 0% 50%; }
                50%  { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def inject_glass_css():
    """Shared glassmorphism styling for cards / forms."""
    st.markdown(
        """
        <style>
        [data-testid="stForm"] {
            background: rgba(255, 255, 255, 0.07);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 20px;
            padding: 40px 35px 20px 35px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
        }
        .fixflow-title {
            text-align: center;
            color: #ffffff;
            font-size: 2.3rem;
            font-weight: 800;
            margin-bottom: 0px;
            text-shadow: 0 2px 12px rgba(0,0,0,0.5);
        }
        .fixflow-subtitle {
            text-align: center;
            color: rgba(255,255,255,0.75);
            font-size: 1rem;
            margin-bottom: 28px;
        }
        div[data-testid="stForm"] label, div[data-testid="stForm"] p {
            color: #f0f0f0 !important;
        }
        .stButton>button, [data-testid="stFormSubmitButton"] button {
            background: linear-gradient(90deg, #ff512f, #dd2476);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 10px 0;
            font-weight: 600;
            transition: transform 0.15s ease;
        }
        .stButton>button:hover, [data-testid="stFormSubmitButton"] button:hover {
            transform: scale(1.02);
            filter: brightness(1.1);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# LOGIN PAGE
# ============================================================

def check_credentials(username, password):
    return username in DEMO_USERS and DEMO_USERS[username] == password


def login_page():
    inject_background()
    inject_glass_css()

    col1, col2, col3 = st.columns([1, 1.1, 1])

    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown('<div class="fixflow-title">🔧 FixFlow AI</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="fixflow-subtitle">Agentic Autonomous Bug Fixing Assistant</div>',
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("🔓 Login", use_container_width=True)

            if submitted:
                if check_credentials(username.strip(), password):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username.strip()
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

        st.markdown(
            '<p style="text-align:center;color:rgba(255,255,255,0.5);font-size:0.8rem;">'
            "Demo credentials: admin / admin123 or demo / demo123</p>",
            unsafe_allow_html=True,
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
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1500,
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


def build_code_context(files, max_total_chars=9000, max_file_chars=3000):
    """Build code context for the LLM, capped to stay within Groq's
    free-tier TPM (tokens per minute) limits."""
    context = ""

    for filename, content in files.items():

        if len(context) >= max_total_chars:
            context += "\n\n... (remaining files omitted to fit token limit) ..."
            break

        snippet = content[:max_file_chars]
        if len(content) > max_file_chars:
            snippet += "\n# ... (truncated) ..."

        context += (
            f"\n\n### FILE: {filename}\n"
            f"```python\n{snippet}\n```"
        )

    return context[:max_total_chars]


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

    inject_background()
    inject_glass_css()

    st.markdown(
        f"""
        <div style="background: rgba(0,0,0,0.35); backdrop-filter: blur(6px);
                    border-radius: 16px; padding: 18px 24px; margin-bottom: 10px;">
            <h1 style="color:white;margin:0;">🔧 FixFlow AI</h1>
            <p style="color:rgba(255,255,255,0.8);margin:4px 0 0 0;">
                Agentic Autonomous Bug Detection &amp; Fixing Assistant
                &nbsp;·&nbsp; Logged in as <b>{st.session_state.get('username', 'guest')}</b>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write(
        "Analyze Python code from manual input, uploaded files, "
        "or public GitHub repositories."
    )

    # --------------------------------------------------------
    # SIDEBAR SETUP
    # --------------------------------------------------------

    with st.sidebar:

        st.markdown(f"👤 **{st.session_state.get('username', 'guest')}**")
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("username", None)
            st.rerun()

        st.divider()

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

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        login_page()
    else:
        main()
