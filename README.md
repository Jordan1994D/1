# bgplay: BitChute background player

A small command-line bot that plays BitChute videos in the background. It runs one
headless [mpv](https://mpv.io) player (audio only by default). You queue and
control videos from any terminal, and playback keeps going after you close it.

## Install

You need Python 3.8+, `mpv` and `yt-dlp`:

```bash
# macOS
brew install mpv yt-dlp
# Debian / Ubuntu
sudo apt install mpv && pip install -U yt-dlp
```

Keep yt-dlp up to date (`pip install -U yt-dlp`). BitChute changes its site
from time to time, and an old yt-dlp is the most common cause of failed playback.

Works on Linux and macOS. On Windows, run it under WSL.

## Usage

```bash
./bgplay.py add https://www.bitchute.com/video/VIDEO_ID/   # starts the player and queues the video
./bgplay.py add URL1 URL2 URL3                             # queue several videos
./bgplay.py add-file queue.txt                             # queue every URL in a file

./bgplay.py status        # what's playing, position, volume
./bgplay.py list          # show the queue
./bgplay.py pause | resume | toggle
./bgplay.py next | prev
./bgplay.py volume 60
./bgplay.py loop on       # repeat the whole queue
./bgplay.py shuffle
./bgplay.py clear         # empty the queue, keep the player running
./bgplay.py stop          # quit the player
./bgplay.py web           # open the web control page
```

To watch video instead of listening to audio only, start the player with
`./bgplay.py start --video`. Do this before you add anything to the queue.

## Web page

```bash
./bgplay.py web
```

This opens a control page at http://localhost:8765 with play/pause, skip, a
seek bar, volume, loop, shuffle, a box to paste links into, and the queue
(click a track to jump to it). Press Ctrl+C to close the page server; the music keeps playing.

By default only your own computer can open the page. To control it from your
phone on the same Wi-Fi, run `./bgplay.py web --host 0.0.0.0` and open
`http://<your-computer's-IP>:8765`. Anyone on that network can then use it, so
only do this on a network you trust.

## Queue files

Put one URL per line. Lines that start with `#` are ignored. See `queue.example.txt`.

## Configuration

| Variable | Purpose |
|---|---|
| `BGPLAY_DIR` | Where the control socket and `mpv.log` are kept (default `~/.bgplay`) |
| `BGPLAY_MPV_ARGS` | Extra mpv options, e.g. `"--ao=pulse --cache=yes"` |

If a video won't play, check `~/.bgplay/mpv.log`.
