import os, base64, requests, zipfile, subprocess, time, json
from pathlib import Path
from audio_gen import generate_audio

PANELS_DIR = Path("panels")
WORK_DIR   = Path("workspace")
OUTPUT_DIR = Path("output")

# ─────────────────────────────────────────────
# 1. AI: Better prompt — scene-accurate narration
# ─────────────────────────────────────────────
def analyze_and_narrate(image_b64):
    api_key = os.environ.get("OPENROUTER_KEY")
    url     = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    prompt = """You are a manga recap narrator. Look at this panel carefully.

Return ONLY a valid JSON object with these exact keys:
{
  "is_junk": "YES or NO",
  "script": "2-3 sentences",
  "action_y": 0
}

RULES:
- "is_junk": Set to "YES" if this is a chapter title page, credits, blank page, logo, or has no story content. Otherwise "NO".
- "script": Describe EXACTLY what is visually happening in THIS panel — who is present, what action is occurring, what emotion is shown. Do NOT invent things not visible. Do NOT be generic. Match the narration to what you actually see.
- "action_y": Vertical percentage (0-100) of the most important face or action in the image. 0=top, 100=bottom. Use 40 if unsure.

Bad example script: "The hero faces a powerful enemy in an intense battle."
Good example script: "A silver-haired man in a black coat stands still, eyes closed, as dozens of glowing blue meteors rain down around him. His expression is calm despite the destruction."

Only return the JSON. No extra text."""

    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": [
            {"type": "text",      "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]}],
        "response_format": {"type": "json_object"}
    }

    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=data, timeout=45)
            if r.status_code == 200:
                raw = r.json()['choices'][0]['message']['content']
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    parsed = parsed[0]
                # Validate required keys
                if all(k in parsed for k in ("is_junk", "script", "action_y")):
                    parsed["action_y"] = max(0, min(100, int(parsed["action_y"])))
                    return parsed
        except Exception as e:
            print(f"  ⚠️ API attempt {attempt+1} failed: {e}")
        time.sleep(5)

    return {"is_junk": "YES", "script": "", "action_y": 40}


# ─────────────────────────────────────────────
# 2. Get exact audio duration via ffprobe
# ─────────────────────────────────────────────
def get_duration(path):
    res = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         str(path)],
        capture_output=True, text=True
    )
    try:
        return float(res.stdout.strip())
    except:
        return 10.0


# ─────────────────────────────────────────────
# 3. Build clip — audio-synced, no cuts
# ─────────────────────────────────────────────
def build_clip(img_path, aud_path, out_path, action_y):
    duration = get_duration(aud_path)
    # Add 0.3s buffer so audio never gets clipped at the end
    total_dur = duration + 0.3

    fps        = 25
    total_frames = int(fps * total_dur)

    # Safe crop: clamp crop Y so it never goes out of bounds
    # action_y is 0-100 representing where the face is vertically
    # We crop a 1920-tall window from a scaled 1080-wide image
    # The crop offset moves the window toward the action point
    crop_y_expr = f"max(0, min(ih-1920, ih*{action_y}/100 - 960))"

    # zoompan: slow subtle zoom, d=total_frames so it lasts full audio
    # s=1080x1920 for portrait/Reels format
    vf = (
        f"scale=1080:-2,"                                    # scale width to 1080, keep ratio
        f"pad=1080:max(ih\\,1920):0:(max(ih\\,1920)-ih)/2," # pad height to at least 1920
        f"crop=1080:1920:0:{crop_y_expr},"                  # crop to portrait with smart Y
        f"zoompan=z='1+0.0003*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s=1080x1920:fps={fps}"          # zoom lasts exactly full duration
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(img_path),
        "-i", str(aud_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-t", str(total_dur),          # video length = audio length + buffer
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",                   # safety: stop at shorter of video/audio
        str(out_path)
    ]

    print(f"  ⏱️  Duration: {duration:.2f}s | Frames: {total_frames} | CropY: {action_y}%")
    subprocess.run(cmd, check=True)


# ─────────────────────────────────────────────
# 4. Main pipeline
# ─────────────────────────────────────────────
def run():
    WORK_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_clips = []

    cbz_files = sorted(PANELS_DIR.glob("*.cbz"))
    if not cbz_files:
        print("❌ No .cbz files found in panels/")
        return

    for cbz in cbz_files:
        print(f"\n📚 Chapter: {cbz.stem}")
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(extract_to)

        imgs = sorted([
            f for f in extract_to.rglob("*")
            if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')
        ])

        # Process up to 6 panels per chapter
        processed = 0
        for img in imgs:
            if processed >= 6:
                break

            print(f"\n🎬 Panel: {img.name}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            try:
                ai_data = analyze_and_narrate(b64)

                if ai_data.get("is_junk") == "YES":
                    print(f"  ⏭️  Skipping junk panel")
                    continue

                script = ai_data.get("script", "").strip()
                if not script:
                    print(f"  ⏭️  Empty script, skipping")
                    continue

                print(f"  📝 Script: {script[:80]}...")

                aud_path = WORK_DIR / f"{cbz.stem}_{img.stem}.mp3"
                if not generate_audio(script, "am_adam", aud_path):
                    print(f"  ❌ Audio generation failed")
                    continue

                clip_path = WORK_DIR / f"{cbz.stem}_{img.stem}.mp4"
                build_clip(img, aud_path, clip_path, ai_data["action_y"])
                all_clips.append(clip_path)
                processed += 1

            except Exception as e:
                print(f"  ⚠️  Error on {img.name}: {e}")

    # ── Merge all clips ──
    if not all_clips:
        print("\n❌ No clips were generated.")
        return

    print(f"\n🎞️  Merging {len(all_clips)} clips...")
    list_file = WORK_DIR / "list.txt"
    with open(list_file, "w") as f:
        for clip in all_clips:
            f.write(f"file '{clip.absolute()}'\n")

    final_out = OUTPUT_DIR / "Omniscient_Reader_Recap.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(final_out)
    ], check=True)

    print(f"\n✅ Final video: {final_out}")


if __name__ == "__main__":
    run()
