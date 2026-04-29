import os, base64, requests, zipfile, subprocess, shutil
from pathlib import Path
from audio_gen import generate_audio

PANELS_DIR = Path("panels")
WORK_DIR = Path("workspace")

def get_narration(image_b64):
    api_key = os.environ.get("OPENROUTER_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Narrate this manga panel for a YouTube recap. Focus on the action!"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']

def build_clip(img, aud, out):
    vf = "scale=1280:-1,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", "5", "-pix_fmt", "yuv420p", str(out)
    ], check=True)

def run():
    print(f"🚀 Starting Pipeline... checking {PANELS_DIR.absolute()}")
    if not PANELS_DIR.exists():
        print(f"❌ ERROR: {PANELS_DIR} folder not found!")
        return

    WORK_DIR.mkdir(exist_ok=True)
    cbz_files = sorted(list(PANELS_DIR.glob("*.cbz")))
    print(f"🔍 Found {len(cbz_files)} CBZ files")

    for cbz in cbz_files:
        print(f"📦 Extracting {cbz.name}...")
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(extract_to)
        
        imgs = sorted([f for f in extract_to.glob("*") if f.suffix.lower() in ['.jpg', '.png', '.jpeg']])[:2]
        for i, img in enumerate(imgs):
            print(f"🖼️ Analyzing image: {img.name}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            try:
                text = get_narration(b64)
                aud = WORK_DIR / f"{cbz.stem}_{i}.mp3"
                if generate_audio(text, "am_adam", aud):
                    build_clip(img, aud, WORK_DIR / f"{cbz.stem}_{i}.mp4")
                    print(f"✅ Created: {cbz.stem}_{i}.mp4")
            except Exception as e:
                print(f"⚠️ Error on panel {i}: {e}")

if __name__ == "__main__":
    run()
    
