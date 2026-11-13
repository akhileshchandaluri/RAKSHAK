"""Start the local Rakshak server and open the dashboard when it is ready."""

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    host, port = "127.0.0.1", 8000
    url = f"http://{host}:{port}"
    with socket.socket() as probe:
        if probe.connect_ex((host, port)) == 0:
            raise SystemExit(f"Port {port} is already in use. Stop the existing server and retry.")

    backend = Path(__file__).resolve().parent / "backend"
    with subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", host, "--port", str(port)],
        cwd=backend,
    ) as process:
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen(url + "/api/status", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(0.2)
            else:
                raise SystemExit("Rakshak did not start. Check the server output above.")
            print(f"Rakshak is running at {url}. Press Ctrl+C to stop.", flush=True)
            webbrowser.open(url + "/index.html")
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    sys.exit(main())
