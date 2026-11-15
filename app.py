import csv
import subprocess
import shutil
import random
import time
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Guess the Song 🎧", page_icon="🎧", layout="centered")
ROOT = Path(__file__).parent
CUSTOM_DIR = ROOT / "songs"
SCORES = ROOT / "leaderboard.csv"
ROUND_COUNT = 5
TIME_LIMIT = 25

st.markdown("""
<style>
.stApp {background: radial-gradient(circle at 15% 0%, #25164d 0, #0c1020 48%, #080b16 100%); color: #f3f0ff;}
.block-container {max-width: 780px; padding-top: 2rem;}
.hero {border:1px solid #5b447d; border-radius:22px; padding:26px; background:linear-gradient(110deg,#33205c,#10172d); margin-bottom:18px;}
.hero h1 {font-size:clamp(2rem,5vw,3.2rem); margin:0; color:#fff;}
.hero p {color:#c6b9e5; margin:8px 0 0;}
.pill {display:inline-block; background:#4c2c83; color:#eadcff; padding:5px 12px; border-radius:999px; font-size:0.8rem; font-weight:700;}
[data-testid="stMetric"] {border:1px solid #42335b; border-radius:15px; padding:13px; background:#171428;}
.stButton > button {border-radius:12px; min-height:46px; font-weight:700;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_custom():
    manifest = CUSTOM_DIR / "songs.csv"
    if not manifest.exists():
        return []
    entries = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            filename = Path((row.get("filename") or "").strip()).name
            path = CUSTOM_DIR / filename
            title = (row.get("title") or "").strip()
            artist = (row.get("artist") or "Unknown").strip()
            if filename and title and path.is_file() and path.suffix.lower() in (".mp3", ".wav", ".ogg"):
                entries.append({"title":title, "artist":artist, "path":str(path)})
    return entries

CLIP_SECONDS = 10  # Change to 5 for hard mode or 15 for easy mode.

@st.cache_data(show_spinner=False)
def custom_clip(path: str, clip_start: float, seconds: int) -> bytes:
    """Decode only a short MP3 excerpt, not the entire recording."""
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
               "-ss", str(clip_start), "-i", path, "-t", str(seconds),
               "-vn", "-codec:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "pipe:1"]
    result = subprocess.run(command, capture_output=True, check=True)
    return result.stdout

@st.cache_data(show_spinner=False)
def song_duration(path: str) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                            capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def audio_for(song, game, round_index):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        st.error("FFmpeg is required to create clips. Install it with: brew install ffmpeg (Mac), or see README.md.")
        st.stop()
    path = song["path"]
    try:
        duration = song_duration(path)
        # Select a point after the intro where possible, but never run past the end.
        latest_start = max(0.0, duration - CLIP_SECONDS)
        earliest_start = min(15.0, latest_start)
        rng = random.Random(f"{game['clip_seed']}:{round_index}")
        clip_start = round(rng.uniform(earliest_start, latest_start), 2)
        return custom_clip(path, clip_start, CLIP_SECONDS)
    except (subprocess.CalledProcessError, ValueError, OSError) as exc:
        st.error(f"Couldn't create an audio clip from {Path(path).name}: {exc}")
        st.stop()

def start_game(name):
    songs = load_custom()
    if len(songs) < 4:
        st.error("Add at least four valid songs to songs/songs.csv before playing.")
        return
    rng = random.Random()
    selection = rng.sample(range(len(songs)), min(ROUND_COUNT, len(songs)))
    st.session_state.game = {"name":name[:30], "mode":"My uploaded clips", "order":selection,
                             "round":0, "score":0, "feedback":None,
                             "started":time.time(), "clip_seed":random.randrange(10**12), "finished":False, "saved":False}
    st.rerun()

def next_round():
    game = st.session_state.game
    game["round"] += 1
    game["feedback"] = None
    game["started"] = time.time()
    if game["round"] >= len(game["order"]):
        game["finished"] = True
    st.rerun()

def save_score(game):
    try:
        write_header = not SCORES.exists()
        with SCORES.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if write_header:
                writer.writerow(["name","score","total","mode","date"])
            writer.writerow([game["name"],game["score"],len(game["order"])*100,game["mode"],time.strftime("%Y-%m-%d %H:%M")])
    except OSError:
        st.warning("This hosting environment does not allow saving the leaderboard locally.")

def leaderboard():
    if not SCORES.exists():
        st.info("No scores yet. Be the first to play!")
        return
    with SCORES.open(encoding="utf-8", newline="") as file:
        scores = list(csv.DictReader(file))
    scores.sort(key=lambda x:int(x.get("score",0)), reverse=True)
    for i, entry in enumerate(scores[:10], 1):
        st.write(f"**#{i} {entry['name']}** — {entry['score']} / {entry['total']} · {entry['mode']}")

st.markdown('<div class="hero"><span class="pill">🎵 STREAMLIT MUSIC GAME</span><h1>Guess the Song 🎧</h1><p>Listen. Guess. Score. Can you go 5 for 5?</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🎛️ Game settings")
    st.caption("Playing tracks from songs/songs.csv. Use audio files you have permission to share.")
    st.divider()
    st.header("🏆 Leaderboard")
    leaderboard()
    st.divider()
    if st.button("🔄 New game", use_container_width=True):
        st.session_state.pop("game", None)
        st.rerun()

# Reset an old game that was started in demo mode before this update.
if "game" in st.session_state and st.session_state.game.get("mode") != "My uploaded clips":
    st.session_state.pop("game", None)

if "game" not in st.session_state:
    st.subheader("Ready for the challenge?")
    player = st.text_input("Your nickname", value="Music Master", max_chars=30)
    st.info("Each round gives you four choices. Faster correct answers earn more points, up to 100 per round.")
    st.caption(f"Songs found: {len(load_custom())}. Add more in songs/songs.csv.")
    if st.button("▶ Start playing", type="primary", use_container_width=True, disabled=not player.strip()):
        start_game(player.strip())
else:
    game = st.session_state.game
    songs = load_custom()
    if game["finished"]:
        st.balloons()
        st.title("🎉 Game over!")
        st.metric("Final score", f"{game['score']} / {len(game['order'])*100}")
        if not game["saved"]:
            save_score(game)
            game["saved"] = True
        st.write("Check the sidebar for the leaderboard!")
        if st.button("Play again", type="primary", use_container_width=True):
            start_game(game["name"])
    else:
        idx = game["order"][game["round"]]
        answer = songs[idx]
        elapsed = time.time() - game["started"]
        remaining = max(0, TIME_LIMIT - int(elapsed))
        top_a, top_b = st.columns(2)
        top_a.metric("Round", f"{game['round'] + 1} / {len(game['order'])}")
        top_b.metric("Score", game["score"])
        st.progress((game["round"])/len(game["order"]))
        st.subheader("🎧 Listen to this clip")
        st.audio(audio_for(answer, game, game["round"]), format="audio/mp3")
        if game["feedback"] is None:
            st.caption(f"⏱️ {TIME_LIMIT} seconds per round. Timer is checked when you submit an answer.")
            # Fixed deterministic options per game/round to survive Streamlit reruns.
            others = [i for i in range(len(songs)) if i != idx]
            r = random.Random(f"{game['name']}:{game['started']}:{game['round']}:options")
            choices = r.sample(others, 3) + [idx]
            r.shuffle(choices)
            with st.form(key=f"answer-{game['round']}"):
                chosen = st.radio("Which song is it?", options=choices,
                                  format_func=lambda i: f"{songs[i]['title']} — {songs[i]['artist']}",
                                  index=None)
                submitted = st.form_submit_button("Lock in answer 🔒", type="primary", use_container_width=True)
            if submitted:
                if chosen is None:
                    st.warning("Choose an answer first.")
                else:
                    elapsed = time.time() - game["started"]
                    valid = elapsed <= TIME_LIMIT
                    correct = chosen == idx and valid
                    earned = max(20, 100 - int(elapsed * 3)) if correct else 0
                    game["score"] += earned
                    game["feedback"] = {"correct":correct,"earned":earned,"timeout":not valid}
                    st.rerun()
        else:
            feedback = game["feedback"]
            if feedback["timeout"]:
                st.error(f"⏰ Time's up! The answer was **{answer['title']}**.")
            elif feedback["correct"]:
                st.success(f"🔥 Correct! **{answer['title']}** · +{feedback['earned']} points")
            else:
                st.error(f"Not quite! The correct answer was **{answer['title']}**.")
            if st.button("Next round →" if game["round"] + 1 < len(game["order"]) else "See results 🏆",
                         type="primary", use_container_width=True):
                next_round()

st.divider()
st.caption("Made for a school project · Streamlit + Python · Your uploaded MP3 library · Leaderboard stored locally (not persistent in cloud)")
