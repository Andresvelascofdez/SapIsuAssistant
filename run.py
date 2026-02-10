"""
Launch script for SAP IS-U Assistant.

Starts all required services and opens the web application in the browser.

Usage:
    python run.py
"""
import subprocess
import sys
import time
import urllib.request
import urllib.error
import shutil
import os
import webbrowser
import threading

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
QDRANT_URL = "http://localhost:6333"
QDRANT_HEALTH = f"{QDRANT_URL}/healthz"
COMPOSE_FILE = os.path.join(PROJECT_ROOT, "docker-compose.yml")
APP_URL = "http://localhost:8000"
MAX_WAIT_SECONDS = 60


def _print(msg: str) -> None:
    print(f"[run] {msg}")


def check_python_deps() -> bool:
    """Check that required Python packages are installed."""
    missing = []
    for pkg in ["openai", "qdrant_client", "docx", "pypdf", "tiktoken",
                 "fastapi", "uvicorn", "jinja2"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        _print(f"Missing Python packages: {', '.join(missing)}")
        _print("Install with: pip install -e .[dev]")
        return False
    return True


def check_docker() -> bool:
    """Check that Docker is available and running."""
    docker = shutil.which("docker")
    if not docker:
        _print("ERROR: 'docker' not found in PATH. Install Docker Desktop.")
        return False

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            _print("ERROR: Docker daemon is not running. Start Docker Desktop.")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        _print("ERROR: Could not connect to Docker daemon.")
        return False

    return True


def start_qdrant() -> bool:
    """Start Qdrant via docker-compose."""
    if not os.path.exists(COMPOSE_FILE):
        _print(f"ERROR: docker-compose.yml not found at {COMPOSE_FILE}")
        return False

    _print("Starting Qdrant via docker-compose...")
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:
        # Fallback to docker-compose (v1)
        result = subprocess.run(
            ["docker-compose", "-f", COMPOSE_FILE, "up", "-d"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )

    if result.returncode != 0:
        _print(f"ERROR starting Qdrant: {result.stderr.strip()}")
        return False

    _print("Qdrant container started.")
    return True


def wait_for_qdrant() -> bool:
    """Wait until Qdrant health endpoint responds."""
    _print(f"Waiting for Qdrant at {QDRANT_HEALTH} ...")
    start = time.time()

    while time.time() - start < MAX_WAIT_SECONDS:
        try:
            req = urllib.request.Request(QDRANT_HEALTH, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    _print("Qdrant is healthy.")
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass

        time.sleep(2)

    _print(f"ERROR: Qdrant did not become healthy within {MAX_WAIT_SECONDS}s.")
    return False


def open_browser() -> None:
    """Wait for the web server to be ready, then open the browser."""
    for _ in range(30):
        try:
            req = urllib.request.Request(APP_URL, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status in (200, 307):
                    _print(f"Opening browser at {APP_URL}")
                    webbrowser.open(APP_URL)
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(1)
    _print("WARNING: Could not verify server is running. Open manually: " + APP_URL)
    webbrowser.open(APP_URL)


def launch_app() -> None:
    """Launch the FastAPI web application via uvicorn."""
    _print(f"Launching SAP IS-U Assistant at {APP_URL} ...")

    # Open browser in a background thread (waits for server to start)
    threading.Thread(target=open_browser, daemon=True).start()

    subprocess.run(
        [sys.executable, "-m", "src"],
        cwd=PROJECT_ROOT,
    )


def main() -> int:
    _print("=" * 50)
    _print("SAP IS-U Assistant - Launcher")
    _print("=" * 50)

    # 1. Check Python dependencies
    _print("Checking Python dependencies...")
    if not check_python_deps():
        return 1
    _print("Python dependencies OK.")

    # 2. Check Docker
    _print("Checking Docker...")
    if not check_docker():
        _print("Continuing without Qdrant (vector search will not work).")
        _print("The app will still open for KB management and Kanban.")
        launch_app()
        return 0

    # 3. Start Qdrant
    if not start_qdrant():
        _print("Continuing without Qdrant.")
        launch_app()
        return 0

    # 4. Wait for Qdrant
    if not wait_for_qdrant():
        _print("Qdrant not ready, continuing anyway. Vector search may fail.")

    # 5. Launch app
    launch_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
