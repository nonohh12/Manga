import os, subprocess
from pathlib import Path

def generate_audio(text, voice, out_path):
    """Reliable TTS for GitHub Actions"""
    if not text.strip(): return False
    
    # Primary: Edge-TTS (Fast & No API limit)
    voice_map = {
        "am_adam": "en-US-GuyNeural", 
        "af_bella": "en-US-JennyNeural"
    }
    ev = voice_map.get(voice, "en-US-GuyNeural")
    
    try:
        subprocess.run([
            "edge-tts", "--voice", ev, 
            "--text", text, 
            "--write-media", str(out_path)
        ], check=True)
        print(f"✅ Audio generated: {out_path}")
        return True
    except Exception as e:
        print(f"❌ TTS Failed: {e}")
        return False
        
