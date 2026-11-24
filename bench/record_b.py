"""Record Run B in a real console window with ffmpeg (gdigrab), no extra installs.

python bench/record_b.py

Opens a classic console window (kept on top while recording; ffmpeg captures
only that window by its handle), runs bench/record_inner.ps1 in it, records the window to
bench/media/runB-demo-raw.mp4, and watches the main session transcript to log
when the worker is dispatched, when it returns, and when the answer is done.
Afterwards it writes a sped-up MP4, a GIF and PNG stills at those moments.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MEDIA = REPO / "bench" / "media"
PROJECTS = Path.home() / ".claude" / "projects" / "E--AgentRoute"
X, Y, W, H = 0, 0, 1280, 760
FFMPEG = shutil.which("ffmpeg")

user32 = ctypes.windll.user32
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2


def window_titled(title: str):
    """The console sets this title first thing (Claude Code renames it later)."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value == title and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def events(jsonl: Path):
    """(dispatched, returned, done) flags from the main transcript."""
    dispatched = returned = done = False
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            for c in content:
                if c.get("type") == "tool_use" and "agentroute work" in json.dumps(c.get("input")):
                    dispatched = True
                if c.get("type") == "tool_result" and dispatched:
                    returned = True
        if rec.get("type") == "assistant" and msg.get("stop_reason") == "end_turn" and returned:
            done = True
    return dispatched, returned, done


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    raw = MEDIA / "runB-demo-raw.mp4"
    before = {p.name for p in PROJECTS.glob("*.jsonl")}
    console = subprocess.Popen(
        ["conhost.exe", "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(REPO / "bench" / "record_inner.ps1")],
    )
    hwnd = None
    for _ in range(100):
        hwnd = window_titled("AgentRoute demo")
        if hwnd:
            break
        time.sleep(0.2)
    if not hwnd:
        subprocess.run(["taskkill", "/PID", str(console.pid), "/T", "/F"], capture_output=True)
        raise SystemExit("console window not found")
    time.sleep(1.5)  # let `mode con` resize the window first
    user32.SetWindowPos(hwnd, HWND_TOPMOST, X, Y, 0, 0, 0x0040 | 0x0001)  # keep its size
    time.sleep(0.5)

    rec = subprocess.Popen(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", "10",
         "-draw_mouse", "0", "-i", f"hwnd={hwnd:#x}" if isinstance(hwnd, int) else f"hwnd={hwnd}", "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-movflags", "frag_keyframe+empty_moov", str(raw)],
        stdin=subprocess.PIPE,
    )
    t0 = time.monotonic()
    marks: dict[str, float] = {}
    jsonl = None
    deadline = t0 + 900
    while time.monotonic() < deadline:
        time.sleep(1)
        if jsonl is None:
            new = [p for p in PROJECTS.glob("*.jsonl") if p.name not in before]
            jsonl = max(new, key=lambda p: p.stat().st_mtime) if new else None
            continue
        d, r, done = events(jsonl)
        now = time.monotonic() - t0
        if d and "dispatch" not in marks:
            marks["dispatch"] = now
        if r and "worker_result" not in marks:
            marks["worker_result"] = now
        if done:
            marks["final_answer"] = now
            time.sleep(6)
            break
    marks["end"] = time.monotonic() - t0
    rec.stdin.write(b"q")
    rec.stdin.flush()
    rec.wait(timeout=30)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002)
    subprocess.run(["taskkill", "/PID", str(console.pid), "/T", "/F"], capture_output=True)
    (MEDIA / "runB-demo-marks.json").write_text(
        json.dumps({"session": jsonl.name if jsonl else None, "seconds": marks}, indent=2))

    # Stills a few seconds after each moment.
    for name, t in marks.items():
        if name == "end":
            continue
        at = min(t + 3, marks["end"] - 0.5)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{at:.1f}", "-i", str(raw),
                        "-frames:v", "1", str(MEDIA / f"runB-{name}.png")])
    # Speed up to about 45 seconds.
    speed = max(1.0, marks["end"] / 45)
    fast = MEDIA / "runB-demo.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(raw), "-vf", f"setpts=PTS/{speed:.2f}",
                    "-r", "15", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(fast)])
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(fast), "-vf",
                    "fps=8,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
                    str(MEDIA / "runB-demo.gif")])
    print(json.dumps(marks, indent=2), f"speed x{speed:.1f}")


if __name__ == "__main__":
    main()
