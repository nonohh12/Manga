import os, base64, requests, zipfile, json, subprocess
from pathlib import Path
from audio_gen import generate_audio

# Paths
PANELS_DIR = Path("panels")
WORK_DIR = Path("workspace")
OUTPUT_DIR = Path("output")

def get_narration_openrouter(image_b64):
    """OpenRouter API: Using Gemini 2.0 Flash (Fast & Modern)"""
    api_key = os.environ.get("OPENROUTER_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Narrate this manga panel dramatically for a YouTube recap. Focus on the action and Dokja's thoughts."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    return r.json()['choices'][0]['message']['content']

def build_video_clip(img_path, aud_path, out_path):
    """Claude's FIXED FFmpeg Filter: Adding Ken Burns Zoom"""
    # Dynamic duration based on audio
    duration = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(aud_path)], capture_output=True, text=True).stdout.strip()
    
    # Professional Zoom Filter
    vf = "scale=8000:-1,zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125,scale=1080:1920"
    
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-i", str(aud_path),
        "-vf", vf, "-c:v", "libx264", "-t", duration, "-pix_fmt", "yuv420p", str(out_path)
    ])

def run_factory():
    WORK_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Process each CBZ
    for cbz in sorted(PANELS_DIR.glob("*.cbz")):
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(WORK_DIR / cbz.stem)
        
        images = sorted((WORK_DIR / cbz.stem).glob("*.jpg"))[:10] # 10 panels for testing
        for i, img in enumerate(images):
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            text = get_narration_openrouter(b64)
            aud = WORK_DIR / f"aud_{i}.mp3"
            generate_audio(text, "am_adam", aud)
            
            clip = WORK_DIR / f"clip_{i}.mp4"
            build_video_clip(img, aud, clip)
            print(f"✅ Created Clip {i}")

if __name__ == "__main__":
    run_factory()
  
