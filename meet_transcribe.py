#!/usr/bin/env python3
"""
meet_transcribe.py — транскрипція WAV файлу через transformers Whisper.

Використання:
    python meet_transcribe.py                    # останній WAV з сьогоднішньої папки
    python meet_transcribe.py path/to/file.wav   # конкретний файл
"""

from __future__ import annotations

import sys
import datetime
from pathlib import Path

import torch
import yaml
import soundfile as sf
from transformers import pipeline

# ============ Конфігурація ============
_cfg: dict = {}
_config_path = Path(__file__).parent / "config.yaml"
if _config_path.exists():
    _cfg = yaml.safe_load(_config_path.read_text(encoding="utf-8")) or {}

MODEL_NAME = _cfg.get("offline_model", "openai/whisper-large-v3")
LANGUAGE = "uk"
BEAM_SIZE = 5

OUTPUT_DIR = Path.home() / "Documents" / "MeetTranscripts"
GLOSSARY_FILE = Path(__file__).parent / "it_glossary_uk.txt"


def find_latest_wav() -> Path | None:
    today = datetime.date.today().strftime("%Y-%m-%d")
    dated_dir = OUTPUT_DIR / today
    if not dated_dir.exists():
        return None
    wavs = sorted(dated_dir.glob("meet_*.wav"))
    return wavs[-1] if wavs else None


def main() -> None:
    if len(sys.argv) > 1:
        wav_path = Path(sys.argv[1])
    else:
        wav_path = find_latest_wav()
        if not wav_path:
            print("❌ WAV файл не знайдено. Вкажи шлях: python meet_transcribe.py path/to/file.wav")
            sys.exit(1)
        print(f"📂 Знайдено: {wav_path}")

    if not wav_path.exists():
        print(f"❌ Файл не існує: {wav_path}")
        sys.exit(1)

    md_path = wav_path.with_suffix(".md")

    initial_prompt = ""
    if GLOSSARY_FILE.exists():
        initial_prompt = GLOSSARY_FILE.read_text(encoding="utf-8").strip()
        print(f"📚 Завантажено словник: {len(initial_prompt)} символів")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "mps" else torch.float32

    print(f"📦 Завантаження моделі: {MODEL_NAME} ({device})")
    pipe = pipeline(
        "automatic-speech-recognition",
        model=MODEL_NAME,
        dtype=torch_dtype,
        device=device,
    )
    print("✅ Модель готова\n")
    print(f"🔄 Транскрипція: {wav_path.name}")
    print("─" * 60)

    audio, sample_rate = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    inputs = {"array": audio, "sampling_rate": sample_rate}

    generate_kwargs: dict = {"language": LANGUAGE, "task": "transcribe", "num_beams": BEAM_SIZE}
    if initial_prompt:
        prompt_ids = pipe.tokenizer.get_prompt_ids(initial_prompt, return_tensors="pt")
        generate_kwargs["prompt_ids"] = prompt_ids.to(device)

    result = pipe(
        inputs,
        generate_kwargs=generate_kwargs,
        return_timestamps=True,
        chunk_length_s=30,
        ignore_warning=True,
    )

    session_dt = datetime.datetime.now()
    md_lines = [
        f"# Транскрипція Meet — {session_dt.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"_Модель: {MODEL_NAME} · Мова: {LANGUAGE}_",
        "",
        "---",
        "",
    ]

    chunks = result.get("chunks", [])
    if chunks:
        for chunk in chunks:
            ts_start = chunk["timestamp"][0] or 0
            ts = str(datetime.timedelta(seconds=int(ts_start)))
            text = chunk["text"].strip()
            if text:
                line = f"[{ts}] {text}"
                print(line)
                md_lines.append(line)
                md_lines.append("")
    else:
        text = result["text"].strip()
        print(text)
        md_lines.append(text)
        md_lines.append("")

    md_lines += [
        "---",
        f"_Завершено: {datetime.datetime.now().strftime('%H:%M:%S')}_",
    ]

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print("─" * 60)
    print(f"✅ Збережено: {md_path}")


if __name__ == "__main__":
    main()
