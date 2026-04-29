import os, subprocess
from pathlib import Path

def generate_audio(text, voice, out_path):
    """Claude's Stable TTS logic with Open-Source Fallback"""
    if not text.strip(): return False
    
    # Try Kokoro first (Best Quality)
    try:
        from kokoro import KPipeline
        import soundfile as sf
        pipeline = KPipeline(lang_code='a')
        generator = pipeline(text, voice=voice, speed=1.0)
        for _, _, audio in generator:
            sf.write(out_path, audio, 24000)
        return True
    except Exception as e:
        print(f"⚠️ Kokoro skip: {e}")
        
        # Edge-TTS Fallback (Reliable for GitHub Actions)
        voice_map = {"am_adam": "en-US-GuyNeural", "af_bella": "en-US-JennyNeural"}
        ev = voice_map.get(voice, "en-US-GuyNeural")
        subprocess.run(["edge-tts", "--voice", ev, "--text", text, "--write-media", str(out_path)])
        return True
      
