import os, base64, requests, zipfile, subprocess
from pathlib import Path
from audio_gen import generate_audio

# Correct Paths
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
                {"type": "text", "text": "Narrate this manga panel dramatically for a YouTube recap."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    return r.json()['choices'][0]['message']['content']

def build_clip(img, aud, out):
    # Ken Burns Effect logic
    vf = "scale=3000:-1,zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125,scale=1080:1920"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", "5", "-pix_fmt", "yuv420p", str(out)
    ], check=True)

def run():
    WORK_DIR.mkdir(exist_ok=True)
    cbz_files = sorted(list(PANELS_DIR.glob("*.cbz")))
    print(f"🔍 Found {len(cbz_files)} chapters")

    for cbz in cbz_files:
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(extract_to)
        
        # Process first 3 images for a quick test
        imgs = sorted([f for f in extract_to.glob("*") if f.suffix.lower() in ['.jpg', '.png']])[:3]
        for i, img in enumerate(imgs):
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            text = get_narration(b64)
            aud = WORK_DIR / f"{cbz.stem}_{i}.mp3"
            if generate_audio(text, "am_adam", aud):
                build_clip(img, aud, WORK_DIR / f"{cbz.stem}_{i}.mp4")
                print(f"✅ Clip Done: {cbz.stem}_{i}")

if __name__ == "__main__":
    run()
            
