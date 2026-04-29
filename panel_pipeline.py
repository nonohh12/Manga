import os, base64, requests, zipfile, subprocess, time, json
from pathlib import Path
from audio_gen import generate_audio

PANELS_DIR = Path("panels")
WORK_DIR = Path("workspace")
OUTPUT_DIR = Path("output")

def analyze_and_narrate(image_b64):
    api_key = os.environ.get("OPENROUTER_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    # We ask the AI to be our editor: filter out junk and find the action
    prompt = """
    1. Is this a credit page, chapter title, or advertisement? (Answer: YES or NO)
    2. If NO, describe the main action in 3 dramatic sentences.
    3. Tell me the vertical percentage (0-100) where the main face or action is located.
    Return as JSON: {"is_junk": "YES/NO", "script": "...", "action_y": 20}
    """
    
    data = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]}],
        "response_format": { "type": "json_object" }
    }
    
    for _ in range(3):
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        time.sleep(5)
    return '{"is_junk": "YES", "script": "", "action_y": 0}'

def build_human_style_clip(img, aud, out, action_y):
    duration = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(aud)], capture_output=True, text=True).stdout.strip()
    
    # Calculate start position based on AI's 'action_y'
    # This prevents scrolling through the whole empty space
    start_y = f"(ih*({action_y}/100))"
    
    vf = (
        f"scale=1440:-1," # Upscale for quality
        f"crop=1080:1920:0:min(ih-oh\, {start_y})," # Focus on the action zone
        f"zoompan=z='1.1+0.1*sin(2*pi*t/{duration})':d=1:s=1080x1920" # Subtle human-like camera shake/zoom
    )
    
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", duration, "-pix_fmt", "yuv420p", str(out)
    ], check=True)

def run():
    WORK_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_clips = []
    
    for cbz in sorted(PANELS_DIR.glob("*.cbz")):
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z: z.extractall(extract_to)
        
        imgs = sorted([f for f in extract_to.rglob("*") if f.suffix.lower() in ['.jpg', '.png', '.webp']])
        for i, img in enumerate(imgs[:10]): # Scan more images but skip junk
            print(f"🎬 Human-AI Editor checking: {img.name}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            res = json.loads(analyze_and_narrate(b64))
            
            if res['is_junk'] == "YES" or not res['script']:
                print(f"  ⏭️ Skipping junk/logo: {img.name}")
                continue
                
            aud = WORK_DIR / f"{cbz.stem}_{i}.mp3"
            if generate_audio(res['script'], "am_adam", aud):
                out_mp4 = WORK_DIR / f"{cbz.stem}_{i}.mp4"
                build_human_style_clip(img, aud, out_mp4, res['action_y'])
                all_clips.append(out_mp4)

    if all_clips:
        with open(WORK_DIR / "list.txt", "w") as f:
            for clip in all_clips: f.write(f"file '{clip.name}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(WORK_DIR / "list.txt"), "-c", "copy", str(OUTPUT_DIR / "Omniscient_Reader_Recap.mp4")], check=True)

if __name__ == "__main__":
    run()
    
