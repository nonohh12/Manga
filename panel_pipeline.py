import os, base64, requests, zipfile, subprocess
from pathlib import Path
from audio_gen import generate_audio

# Paths
PANELS_DIR = Path("panels")
WORK_DIR = Path("workspace")

def get_narration(image_b64):
    api_key = os.environ.get("OPENROUTER_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Narrate this manga panel dramatically for a YouTube recap. Focus on the action!"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']

def build_clip(img, aud, out):
    # Standard 9:16 format for Reels/Shorts
    vf = "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", "5", "-pix_fmt", "yuv420p", str(out)
    ], check=True)

def run():
    print(f"🚀 Starting Pipeline...")
    WORK_DIR.mkdir(exist_ok=True)
    
    cbz_files = sorted(list(PANELS_DIR.glob("*.cbz")))
    print(f"🔍 Found {len(cbz_files)} CBZ files")

    for cbz in cbz_files:
        extract_to = WORK_DIR / cbz.stem
        print(f"📦 Extracting {cbz.name} to {extract_to}")
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(extract_to)
        
        # Check all images (jpg, png, webp)
        imgs = sorted([f for f in extract_to.rglob("*") if f.suffix.lower() in ['.jpg', '.png', '.jpeg', '.webp']])
        print(f"🖼️ Found {len(imgs)} images in {cbz.stem}")
        
        # Test: Process only first 2 images to ensure success
        for i, img in enumerate(imgs[:2]):
            print(f"  👉 Analyzing: {img.name}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            try:
                text = get_narration(b64)
                print(f"  📝 AI Text: {text[:50]}...")
                aud = WORK_DIR / f"{cbz.stem}_{i}.mp3"
                if generate_audio(text, "am_adam", aud):
                    out_mp4 = WORK_DIR / f"{cbz.stem}_{i}.mp4"
                    build_clip(img, aud, out_mp4)
                    print(f"  ✅ Clip created: {out_mp4.name}")
            except Exception as e:
                print(f"  ⚠️ Error: {e}")

if __name__ == "__main__":
    run()
    
