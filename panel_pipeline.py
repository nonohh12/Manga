import os, base64, requests, zipfile, subprocess, time
from pathlib import Path
from audio_gen import generate_audio

PANELS_DIR = Path("panels")
WORK_DIR = Path("workspace")
OUTPUT_DIR = Path("output")

def get_narration(image_b64):
    api_key = os.environ.get("OPENROUTER_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Narrate this manga panel for a YouTube recap. 3 sentences max."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]}]
    }
    # Retry logic for 429 Errors
    for i in range(3):
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        print(f"⚠️ API Busy (Attempt {i+1})... waiting 5s")
        time.sleep(5)
    return "The story continues with an intense confrontation."

def get_audio_duration(aud_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(aud_path)]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip() or "5.0"

def build_clip(img, aud, out):
    duration = get_audio_duration(aud)
    # FIX: This filter scrolls down the long image so faces don't look squashed
    vf = (
        f"scale=1080:-1,crop=1080:1920:0:'min(ih-oh, (ih-oh)*(t/{duration}))',"
        "format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", duration, "-pix_fmt", "yuv420p", "-shortest", str(out)
    ], check=True)

def run():
    WORK_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_clips = []
    
    for cbz in sorted(PANELS_DIR.glob("*.cbz")):
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z: z.extractall(extract_to)
        
        imgs = sorted([f for f in extract_to.rglob("*") if f.suffix.lower() in ['.jpg', '.png', '.webp']])
        for i, img in enumerate(imgs[:4]): # 4 panels per chapter
            print(f"🎬 Processing {cbz.stem} - Panel {i}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            text = get_narration(b64)
            aud = WORK_DIR / f"{cbz.stem}_{i}.mp3"
            if generate_audio(text, "am_adam", aud):
                out_mp4 = WORK_DIR / f"{cbz.stem}_{i}.mp4"
                build_clip(img, aud, out_mp4)
                all_clips.append(out_mp4)

    if all_clips:
        with open(WORK_DIR / "list.txt", "w") as f:
            for clip in all_clips: f.write(f"file '{clip.name}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(WORK_DIR / "list.txt"), "-c", "copy", str(OUTPUT_DIR / "Omniscient_Reader_Recap.mp4")], check=True)

if __name__ == "__main__":
    run()
