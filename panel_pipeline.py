import os, base64, requests, zipfile, subprocess, json
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
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Narrate this manga panel for a YouTube recap. 3-4 dramatic sentences."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']

def get_audio_duration(aud_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(aud_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def build_clip(img, aud, out):
    duration = get_audio_duration(aud)
    # Filter: High-res zoom + slow pan to cover the long strips
    vf = (
        "scale=1080:-1,"
        "zoompan=z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125:s=1080x1920,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
    )
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", duration, "-pix_fmt", "yuv420p", "-shortest", str(out)
    ], check=True)

def run():
    WORK_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_clips = []
    
    cbz_files = sorted(list(PANELS_DIR.glob("*.cbz")))
    for cbz in cbz_files:
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(extract_to)
        
        imgs = sorted([f for f in extract_to.rglob("*") if f.suffix.lower() in ['.jpg', '.png', '.jpeg', '.webp']])
        
        for i, img in enumerate(imgs[:3]): # Testing 3 panels per chapter
            print(f"🎬 Creating Scene: {cbz.stem} - Panel {i}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            try:
                text = get_narration(b64)
                aud_path = WORK_DIR / f"{cbz.stem}_{i}.mp3"
                if generate_audio(text, "am_adam", aud_path):
                    out_mp4 = WORK_DIR / f"{cbz.stem}_{i}.mp4"
                    build_clip(img, aud_path, out_mp4)
                    all_clips.append(out_mp4)
            except Exception as e:
                print(f"⚠️ Skip panel: {e}")

    if all_clips:
        print("🎞️ Merging all scenes into Final Recap...")
        with open(WORK_DIR / "list.txt", "w") as f:
            for clip in all_clips:
                f.write(f"file '{clip.name}'\n")
        
        final_video = OUTPUT_DIR / "Omniscient_Reader_Recap.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(WORK_DIR / "list.txt"), 
            "-c", "copy", str(final_video)
        ], check=True)
        print(f"✅ PRODUCTION COMPLETE: {final_video}")

if __name__ == "__main__":
    run()
    
