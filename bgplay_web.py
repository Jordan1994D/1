"""Local web control page for bgplay.

Started with `bgplay.py web`. Serves web/index.html and a small JSON API that
forwards commands to the mpv player over its IPC socket.

Only listens on 127.0.0.1 by default. Requests must carry a JSON body and a
matching Host header, which stops other websites (and DNS rebinding) from
driving the player through your browser.
"""

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import bgplay

INDEX_HTML = Path(__file__).with_name("web") / "index.html"
MAX_BODY = 64 * 1024


def player_state():
    if not bgplay.is_running():
        return {"running": False}
    playlist = bgplay.get("playlist", []) or []
    return {
        "running": True,
        "title": bgplay.get("media-title") or bgplay.get("path"),
        "paused": bool(bgplay.get("pause")),
        "idle": bool(bgplay.get("idle-active")),
        "position": bgplay.get("time-pos"),
        "duration": bgplay.get("duration"),
        "volume": bgplay.get("volume"),
        "loop": bgplay.get("loop-playlist") not in (False, "no", None),
        "video": bgplay.get("vid") not in (False, "no", None),
        "queue": [
            {
                "title": e.get("title") or e.get("filename"),
                "url": e.get("filename"),
                "current": bool(e.get("current")),
            }
            for e in playlist
        ],
    }


def run_action(body):
    action = body.get("action")
    if action == "start":
        bgplay.start(video=bool(body.get("video")))
    elif action == "add":
        urls = [u for u in body.get("urls", []) if isinstance(u, str) and u.strip()]
        if not urls:
            raise ValueError("no URLs given")
        bgplay.add(urls)
    elif action == "toggle":
        bgplay.ipc("cycle", "pause")
    elif action == "next":
        bgplay.ipc("playlist-next", "force")
    elif action == "prev":
        bgplay.ipc("playlist-prev", "force")
    elif action == "seek":
        bgplay.ipc("seek", float(body["seconds"]), "absolute")
    elif action == "volume":
        bgplay.ipc("set_property", "volume", max(0, min(130, int(body["level"]))))
    elif action == "loop":
        bgplay.ipc("set_property", "loop-playlist", "inf" if body.get("on") else "no")
    elif action == "shuffle":
        bgplay.ipc("playlist-shuffle")
    elif action == "jump":
        bgplay.ipc("playlist-play-index", int(body["index"]))
    elif action == "remove":
        bgplay.ipc("playlist-remove", int(body["index"]))
    elif action == "clear":
        bgplay.ipc("stop")
        bgplay.ipc("playlist-clear")
    elif action == "stop":
        bgplay.ipc("quit")
        bgplay.SOCKET_PATH.unlink(missing_ok=True)
    else:
        raise ValueError(f"unknown action: {action}")


class Handler(BaseHTTPRequestHandler):
    allowed_hosts = set()

    def log_message(self, *args):
        pass

    def send_json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        if self.allowed_hosts is None or self.headers.get("Host") in self.allowed_hosts:
            return True
        self.send_json(403, {"error": "bad Host header"})
        return False

    def do_GET(self):
        if not self.host_ok():
            return
        if self.path in ("/", "/index.html"):
            data = INDEX_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/state":
            self.send_json(200, player_state())
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self.host_ok():
            return
        if self.path != "/api/cmd":
            return self.send_json(404, {"error": "not found"})
        # Cross-site forms can't send application/json without a CORS preflight,
        # which this server never approves.
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send_json(415, {"error": "expected application/json"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.send_json(413, {"error": "request too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            run_action(body)
        except bgplay.PlayerNotRunning:
            return self.send_json(409, {"error": "Player is not running."})
        except SystemExit as e:  # bgplay.start() exits on missing mpv / yt-dlp
            return self.send_json(500, {"error": str(e.code)})
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            return self.send_json(400, {"error": str(e)})
        self.send_json(200, player_state())


def serve(host="127.0.0.1", port=8765, open_browser=True):
    if host in ("127.0.0.1", "localhost", "::1"):
        Handler.allowed_hosts = {f"localhost:{port}", f"127.0.0.1:{port}", f"[::1]:{port}"}
    else:
        # Listening on the network (e.g. to control it from a phone): any Host goes.
        Handler.allowed_hosts = None
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
    print(f"bgplay web control running at {url}  (Ctrl+C to quit; the player keeps playing)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
