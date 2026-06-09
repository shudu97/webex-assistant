#!/usr/bin/env python3
import sys
import subprocess
import tempfile
import os

def extract_audio(video_path: str, out_wav: str):
    """Extract audio from video to 16kHz mono WAV using ffmpeg."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-ar", "16000", "-ac", "1", "-f", "wav", out_wav,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def transcribe(video_path: str, language: str = "en") -> str:
    from transformers import AutoProcessor, CohereAsrForConditionalGeneration
    from transformers.audio_utils import load_audio

    model_id = "CohereLabs/cohere-transcribe-03-2026"

    print("Loading model (downloads on first run)...")
    processor = AutoProcessor.from_pretrained(model_id)
    model = CohereAsrForConditionalGeneration.from_pretrained(
        model_id, device_map="auto"
    )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        print("Extracting audio from video...")
        extract_audio(video_path, tmp_path)

        print("Transcribing...")
        audio = load_audio(tmp_path, sampling_rate=16000)
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt", language=language)
        inputs = inputs.to(model.device, dtype=model.dtype)

        outputs = model.generate(**inputs, max_new_tokens=512)
        text = processor.decode(outputs, skip_special_tokens=True)
        return text
    finally:
        os.unlink(tmp_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <video_file> [language]")
        print("  language defaults to 'en'")
        print("  supported: en fr de it es pt el nl pl zh ja ko vi ar")
        sys.exit(1)

    video = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"

    result = transcribe(video, lang)
    print("\n--- Transcription ---")
    print(result)
