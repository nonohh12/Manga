import os, base64, requests, zipfile, subprocess, glob
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
                {"type": "text", "text": "Narrate this manga panel dramatically. 2-3 sentences."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']

def build_clip(img, aud, out):
    # FIX: Is filter se lambi images Reels (9:16) mein perfectly fit hongi
    vf = "scale=1080:-1,crop=1080:min(ih\,1920):0:0,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
        "-vf", vf, "-c:v", "libx264", "-t", "5", "-pix_fmt", "yuv420p", "-shortest", str(out)
    ], check=True)

def combine_videos(video_list, final_out):
    # Sabhi clips ko ek lambi video mein jodna
    with open("concat.txt", "w") as f:
        for v in video_list:
            f.write(f"file '{v.absolute()}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", str(final_out)], check=True)

def run():
    WORK_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_clips = []
    
    cbz_files = sorted(list(PANELS_DIR.glob("*.cbz")))
    for cbz in cbz_files:
        extract_to = WORK_DIR / cbz.stem
        with zipfile.ZipFile(cbz, 'r') as z:
            z.extractall(extract_to)
        
        # Sabhi supported images dhoondhna
        imgs = sorted([f for f in extract_to.rglob("*") if f.suffix.lower() in ['.jpg', '.png', '.jpeg', '.webp']])
        
        for i, img in enumerate(imgs[:5]): # Har chapter se 5 panels
            print(f"🎬 Processing: {img.name}")
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            
            try:
                text = get_narration(b64)
                aud = WORK_DIR / f"{cbz.stem}_{i}.mp3"
                if generate_audio(text, "am_adam", aud):
                    out_mp4 = WORK_DIR / f"{cbz.stem}_{i}.mp4"
                    build_clip(img, aud, out_mp4)
                    all_clips.append(out_mp4)
            except Exception as e:
                print(f"⚠️ Skip: {e}")

    if all_clips:
        print("🎞️ Combining all clips into final video...")
        combine_videos(all_clips, OUTPUT_DIR / "final_recap.mp4")

if __name__ == "__main__":
    run()
    
