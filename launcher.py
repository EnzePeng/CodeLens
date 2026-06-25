"""
CodeLens Launcher — Single entry point for the packaged application.

Starts llama-server, then the FastAPI web app, and opens the browser.
Handles graceful shutdown on Ctrl+C or window close.
"""
import configparser
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


def get_base_dir() -> Path:
    """Get the base directory of the application."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def load_config(base_dir: Path) -> configparser.ConfigParser:
    """Load config.ini from the base directory."""
    config = configparser.ConfigParser()
    config_path = base_dir / "config.ini"
    if config_path.exists():
        config.read(config_path, encoding="utf-8")
    else:
        print(f"[WARN] config.ini not found at {config_path}, using defaults")
    return config


def resolve_model_path(config: configparser.ConfigParser, base_dir: Path) -> Path:
    """Resolve the model file path from config."""
    model_str = config.get("llama", "model_path", fallback=r"models\Qwen3.5-9B.Q4_K_M.gguf")
    model_path = Path(model_str)
    if not model_path.is_absolute():
        model_path = base_dir / model_path
    return model_path


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port: int, timeout: float = 60.0) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def start_llama_server(base_dir: Path, config: configparser.ConfigParser) -> subprocess.Popen:
    """Start llama-server.exe as a subprocess."""
    llama_dir = base_dir / "llama-server"
    server_exe = llama_dir / "llama-server.exe"

    if not server_exe.exists():
        print(f"[ERROR] llama-server.exe not found: {server_exe}")
        sys.exit(1)

    model_path = resolve_model_path(config, base_dir)
    if not model_path.exists():
        print(f"[ERROR] Model file not found: {model_path}")
        print("Please download the model and place it in the models/ directory.")
        sys.exit(1)

    port = config.getint("llama", "port", fallback=8080)
    host = config.get("llama", "host", fallback="127.0.0.1")
    context_size = config.getint("llama", "context_size", fallback=16384)
    gpu_layers = config.getint("llama", "gpu_layers", fallback=999)
    batch_size = config.getint("llama", "batch_size", fallback=512)
    ubatch_size = config.getint("llama", "ubatch_size", fallback=256)
    parallel = config.getint("llama", "parallel", fallback=2)
    cache_type_k = config.get("llama", "cache_type_k", fallback="q8_0")
    cache_type_v = config.get("llama", "cache_type_v", fallback="q8_0")
    cache_reuse = config.getint("llama", "cache_reuse", fallback=4000)
    reasoning_format = config.get("llama", "reasoning_format", fallback="none")

    cmd = [
        str(server_exe),
        "-m", str(model_path),
        "-ngl", str(gpu_layers),
        "-c", str(context_size),
        "--host", host,
        "--port", str(port),
        "--jinja",
        "--reasoning-format", reasoning_format,
        "--cache-type-k", cache_type_k,
        "--cache-type-v", cache_type_v,
        "--cache-reuse", str(cache_reuse),
        "--parallel", str(parallel),
        "--batch-size", str(batch_size),
        "--ubatch-size", str(ubatch_size),
    ]

    print(f"[Launcher] Starting llama-server on {host}:{port}...")
    print(f"[Launcher] Model: {model_path}")
    print(f"[Launcher] Command: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        cwd=str(llama_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def _forward_output():
        for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                try:
                    print(f"[llama] {text}")
                except UnicodeEncodeError:
                    print(f"[llama] {text.encode('ascii', errors='replace').decode('ascii')}")

    t = threading.Thread(target=_forward_output, daemon=True)
    t.start()

    return proc


def start_web_app(base_dir: Path, config: configparser.ConfigParser) -> subprocess.Popen:
    """Start the PyInstaller-bundled web app or fallback to python/uvicorn."""
    host = config.get("web", "host", fallback="127.0.0.1")
    port = config.getint("web", "port", fallback=8765)

    # Try bundled app first
    bundled_app = base_dir / "app" / "app.exe"
    if bundled_app.exists():
        cmd = [str(bundled_app)]
    else:
        # Fallback: run via Python (development mode)
        venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
        app_dir = base_dir / "local-coder-web"
        if venv_python.exists() and app_dir.exists():
            cmd = [
                str(venv_python),
                "-m", "uvicorn", "app:app",
                "--app-dir", str(app_dir),
                "--host", host,
                "--port", str(port),
            ]
        else:
            print("[ERROR] Neither bundled app.exe nor venv Python found.")
            sys.exit(1)

    os.environ["HOST"] = host
    os.environ["PORT"] = str(port)

    print(f"[Launcher] Starting web app on {host}:{port}...")

    proc = subprocess.Popen(
        cmd,
        cwd=str(base_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def _forward_output():
        for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                try:
                    print(f"[web] {text}")
                except UnicodeEncodeError:
                    print(f"[web] {text.encode('ascii', errors='replace').decode('ascii')}")

    t = threading.Thread(target=_forward_output, daemon=True)
    t.start()

    return proc


def open_browser(config: configparser.ConfigParser):
    """Open the browser after a short delay."""
    host = config.get("web", "host", fallback="127.0.0.1")
    port = config.getint("web", "port", fallback=8765)
    url = f"http://{host}:{port}"

    def _open():
        time.sleep(2)
        print(f"[Launcher] Opening browser: {url}")
        webbrowser.open(url)

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def main():
    """Main entry point."""
    base_dir = get_base_dir()
    print(f"[Launcher] CodeLens starting from: {base_dir}")

    config = load_config(base_dir)

    llama_port = config.getint("llama", "port", fallback=8080)
    web_port = config.getint("web", "port", fallback=8765)

    # Check if ports are already in use
    if is_port_in_use(llama_port):
        print(f"[WARN] Port {llama_port} already in use, assuming llama-server is running")
        llama_proc = None
    else:
        llama_proc = start_llama_server(base_dir, config)
        print(f"[Launcher] Waiting for llama-server on port {llama_port}...")
        if not wait_for_port(llama_port, timeout=120):
            print(f"[ERROR] llama-server failed to start within 120 seconds")
            if llama_proc:
                llama_proc.kill()
            sys.exit(1)
        print(f"[Launcher] llama-server is ready!")

    if is_port_in_use(web_port):
        print(f"[ERROR] Port {web_port} already in use")
        if llama_proc:
            llama_proc.kill()
        sys.exit(1)

    web_proc = start_web_app(base_dir, config)
    print(f"[Launcher] Waiting for web app on port {web_port}...")
    if not wait_for_port(web_port, timeout=30):
        print(f"[WARN] Web app may still be starting, opening browser anyway...")

    open_browser(config)

    print("=" * 60)
    print("  CodeLens is running!")
    print(f"  Web UI: http://{config.get('web', 'host', fallback='127.0.0.1')}:{web_port}")
    print(f"  LLM API: http://{config.get('llama', 'host', fallback='127.0.0.1')}:{llama_port}")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    def shutdown(signum=None, frame=None):
        print("\n[Launcher] Shutting down...")
        for name, proc in [("llama-server", llama_proc), ("web-app", web_proc)]:
            if proc and proc.poll() is None:
                print(f"[Launcher] Stopping {name} (PID {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("[Launcher] Done.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, shutdown)

    try:
        while True:
            # Check if child processes are still alive
            if llama_proc and llama_proc.poll() is not None:
                print("[WARN] llama-server exited unexpectedly")
                shutdown()
            if web_proc.poll() is not None:
                print("[WARN] Web app exited unexpectedly")
                shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
