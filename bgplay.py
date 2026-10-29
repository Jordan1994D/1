#!/usr/bin/env python3
"""bgplay - play BitChute videos in the background.

Runs a single headless mpv instance (audio only by default) and controls it
over mpv's JSON IPC socket, so playback keeps going after the command exits.
mpv resolves BitChute pages through yt-dlp.

Usage:
    bgplay.py start [--video] [--volume N]
    bgplay.py add URL [URL ...]       add videos to the queue (starts player if needed)
    bgplay.py add-file FILE           add every URL listed in FILE (one per line, # comments)
    bgplay.py pause | resume | toggle
    bgplay.py next | prev
    bgplay.py volume N                set volume 0-130
    bgplay.py loop on|off             loop the whole queue
    bgplay.py shuffle
    bgplay.py status
    bgplay.py list
    bgplay.py clear
    bgplay.py stop                    quit the player
    bgplay.py web [--port N]          open the web control page

Environment:
    BGPLAY_DIR       where the socket and log live (default ~/.bgplay)
    BGPLAY_MPV_ARGS  extra mpv options, e.g. "--ao=pulse --cache=yes"
"""

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("BGPLAY_DIR", Path.home() / ".bgplay"))
SOCKET_PATH = STATE_DIR / "mpv.sock"
LOG_PATH = STATE_DIR / "mpv.log"


class PlayerNotRunning(Exception):
    pass


def ipc(command, *args):
    """Send one command to mpv and return its 'data' field."""
    if not SOCKET_PATH.exists():
        raise PlayerNotRunning
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(str(SOCKET_PATH))
            sock.sendall((json.dumps({"command": [command, *args]}) + "\n").encode())
            buf = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    raise PlayerNotRunning
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line)
                    if "event" in msg:
                        continue
                    if msg.get("error") != "success":
                        raise RuntimeError(f"mpv: {msg.get('error')}")
                    return msg.get("data")
    except (ConnectionRefusedError, FileNotFoundError):
        SOCKET_PATH.unlink(missing_ok=True)
        raise PlayerNotRunning


def get(prop, default=None):
    try:
        return ipc("get_property", prop)
    except RuntimeError:
        return default


def is_running():
    try:
        ipc("get_property", "pid")
        return True
    except PlayerNotRunning:
        return False


def start(video=False, volume=None):
    if is_running():
        print("Player is already running.")
        return
    for tool in ("mpv", "yt-dlp"):
        if not shutil.which(tool):
            sys.exit(f"error: '{tool}' is not installed or not on PATH.")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)

    cmd = [
        "mpv",
        "--idle=yes",
        "--no-terminal",
        "--force-window=no",
        f"--input-ipc-server={SOCKET_PATH}",
        f"--log-file={LOG_PATH}",
        "--ytdl=yes",
    ]
    if not video:
        cmd += ["--no-video", "--ytdl-format=bestaudio/best"]
    if volume is not None:
        cmd.append(f"--volume={volume}")
    cmd += shlex.split(os.environ.get("BGPLAY_MPV_ARGS", ""))

    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach so it survives this shell
    )
    for _ in range(50):
        if is_running():
            print(f"Player started ({'video' if video else 'audio only'}).")
            return
        time.sleep(0.1)
    sys.exit(f"error: mpv did not start; see {LOG_PATH}")


def normalize(url):
    url = url.strip()
    if "bitchute.com" not in url:
        print(f"warning: not a BitChute URL, trying anyway: {url}", file=sys.stderr)
    return url


def add(urls):
    if not is_running():
        start()
    for url in urls:
        ipc("loadfile", normalize(url), "append-play")
        print(f"Queued: {url}")


def read_url_file(path):
    lines = Path(path).read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


def fmt_time(seconds):
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def status():
    playlist = get("playlist", [])
    if not playlist:
        print("Running, queue is empty.")
        return
    title = get("media-title") or get("path") or "(loading)"
    state = "paused" if get("pause") else "playing"
    pos, dur = get("time-pos"), get("duration")
    current = next((i for i, e in enumerate(playlist) if e.get("current")), None)
    print(f"[{state}] {title}")
    print(f"  {fmt_time(pos)} / {fmt_time(dur)}   volume {get('volume', 0):.0f}"
          f"   loop {get('loop-playlist')}")
    if current is not None:
        print(f"  track {current + 1} of {len(playlist)}")


def list_queue():
    playlist = get("playlist", [])
    if not playlist:
        print("Queue is empty.")
    for i, entry in enumerate(playlist, 1):
        marker = ">" if entry.get("current") else " "
        print(f"{marker} {i:>3}. {entry.get('title') or entry.get('filename')}")


def main():
    parser = argparse.ArgumentParser(description="Play BitChute videos in the background.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="start the background player")
    p.add_argument("--video", action="store_true", help="show video instead of audio only")
    p.add_argument("--volume", type=int)

    p = sub.add_parser("add", help="add URLs to the queue")
    p.add_argument("urls", nargs="+")

    p = sub.add_parser("add-file", help="add URLs from a file")
    p.add_argument("file")

    p = sub.add_parser("volume", help="set volume 0-130")
    p.add_argument("level", type=int)

    p = sub.add_parser("loop", help="loop the whole queue")
    p.add_argument("mode", choices=["on", "off"])

    p = sub.add_parser("web", help="open the web control page")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1",
                   help="address to listen on (default: this computer only)")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")

    for name in ("pause", "resume", "toggle", "next", "prev", "shuffle",
                 "status", "list", "clear", "stop"):
        sub.add_parser(name)

    args = parser.parse_args()

    try:
        if args.cmd == "web":
            import bgplay_web
            bgplay_web.serve(args.host, args.port, not args.no_browser)
        elif args.cmd == "start":
            start(args.video, args.volume)
        elif args.cmd == "add":
            add(args.urls)
        elif args.cmd == "add-file":
            add(read_url_file(args.file))
        elif args.cmd == "pause":
            ipc("set_property", "pause", True)
        elif args.cmd == "resume":
            ipc("set_property", "pause", False)
        elif args.cmd == "toggle":
            ipc("cycle", "pause")
        elif args.cmd == "next":
            ipc("playlist-next", "force")
        elif args.cmd == "prev":
            ipc("playlist-prev", "force")
        elif args.cmd == "volume":
            ipc("set_property", "volume", max(0, min(130, args.level)))
        elif args.cmd == "loop":
            ipc("set_property", "loop-playlist", "inf" if args.mode == "on" else "no")
        elif args.cmd == "shuffle":
            ipc("playlist-shuffle")
        elif args.cmd == "status":
            status()
        elif args.cmd == "list":
            list_queue()
        elif args.cmd == "clear":
            ipc("stop")
            ipc("playlist-clear")
        elif args.cmd == "stop":
            ipc("quit")
            SOCKET_PATH.unlink(missing_ok=True)
            print("Player stopped.")
    except PlayerNotRunning:
        sys.exit("Player is not running. Start it with: bgplay.py start  (or just: bgplay.py add URL)")
    except RuntimeError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
