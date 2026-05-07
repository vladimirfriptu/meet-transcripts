#!/usr/bin/env python3
"""
meet_transcribe.py — локальна транскрипція Google Meet українською в реальному часі.

Стек:
    BlackHole (системне аудіо) + мікрофон → Aggregate Device
    → sounddevice → faster-whisper (Yehor/whisper-large-v3-turbo-quantized-uk)
    → live вивід у терміналі + markdown файл у ~/Documents/MeetTranscripts/

Запуск:
    python meet_transcribe.py
    Cmd+C для зупинки і збереження.
"""

from __future__ import annotations

import sys
import time
import queue
import signal
import threading
import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ============ Конфігурація ============
MODEL_NAME = "Yehor/whisper-large-v3-turbo-quantized-uk"  # український fine-tune
FALLBACK_MODEL = "large-v3-turbo"  # запасний варіант, якщо Yehor не завантажиться
LANGUAGE = "uk"
COMPUTE_TYPE = "int8"  # int8 на M-series швидкий і легкий; "float16" якщо хочеш точніше
SAMPLE_RATE = 16000
DEVICE_KEYWORD = "BlackHole"  # підрядок у назві input-пристрою (або Aggregate)
CHUNK_SECONDS = 6  # розмір аудіо-фрагменту для транскрипції
SILENCE_RMS = 0.003  # пропускати тихі чанки
BEAM_SIZE = 5

OUTPUT_DIR = Path.home() / "Documents" / "MeetTranscripts"
GLOSSARY_FILE = Path(__file__).parent / "it_glossary_uk.txt"


# ============ Підготовка ============
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
session_start = datetime.datetime.now()
md_path = OUTPUT_DIR / f"meet_{session_start.strftime('%Y%m%d_%H%M%S')}.md"

initial_prompt = ""
if GLOSSARY_FILE.exists():
    initial_prompt = GLOSSARY_FILE.read_text(encoding="utf-8").strip()
    print(f"📚 Завантажено словник: {len(initial_prompt)} символів")


def find_input_device() -> tuple[int, dict]:
    """Знаходить input-пристрій з ім'ям, що містить DEVICE_KEYWORD."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if (
            DEVICE_KEYWORD.lower() in dev["name"].lower()
            and dev["max_input_channels"] > 0
        ):
            return i, dev
    print(f"❌ Пристрій '{DEVICE_KEYWORD}' не знайдено.\nДоступні input-пристрої:")
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(f"  [{i}] {dev['name']} ({dev['max_input_channels']} ch)")
    sys.exit(1)


def load_model() -> WhisperModel:
    """Завантажує Yehor fine-tune; якщо невдало — fallback на large-v3-turbo."""
    print(f"📦 Завантаження моделі: {MODEL_NAME}")
    try:
        return WhisperModel(MODEL_NAME, device="auto", compute_type=COMPUTE_TYPE)
    except Exception as e:
        print(f"⚠️  Не вдалося завантажити {MODEL_NAME}: {e}")
        print(f"📦 Fallback на: {FALLBACK_MODEL}")
        return WhisperModel(FALLBACK_MODEL, device="auto", compute_type=COMPUTE_TYPE)


# ============ Стан ============
device_idx, device_info = find_input_device()
print(f"🎙  Input: {device_info['name']} (idx={device_idx}, "
      f"native_sr={int(device_info['default_samplerate'])})")

model = load_model()
print("✅ Модель готова\n")

audio_queue: queue.Queue[np.ndarray] = queue.Queue()
buffer = np.zeros(0, dtype=np.float32)
running = True

md_file = open(md_path, "w", encoding="utf-8")
md_file.write(f"# Транскрипція Meet — {session_start.strftime('%Y-%m-%d %H:%M')}\n\n")
md_file.write(f"_Модель: {MODEL_NAME} · Мова: {LANGUAGE}_\n\n---\n\n")
md_file.flush()


# ============ Audio I/O ============
def audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
    if status:
        print(f"⚠️  audio status: {status}", file=sys.stderr)
    audio_queue.put(indata.copy())


# ============ Транскрипція ============
def transcribe_chunk(audio: np.ndarray, t_offset_s: float) -> None:
    if len(audio) < SAMPLE_RATE:  # коротше 1 сек — пропуск
        return
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < SILENCE_RMS:
        return

    segments, _info = model.transcribe(
        audio,
        language=LANGUAGE,
        initial_prompt=initial_prompt,
        beam_size=BEAM_SIZE,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        condition_on_previous_text=False,  # запобігає галюцинаційним петлям у chunked mode
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    if not text:
        return

    ts = str(datetime.timedelta(seconds=int(max(0, t_offset_s))))
    line = f"[{ts}] {text}"
    print(line, flush=True)
    md_file.write(line + "\n\n")
    md_file.flush()


def transcribe_worker() -> None:
    global buffer
    chunk_samples = SAMPLE_RATE * CHUNK_SECONDS
    t0 = time.time()

    while running:
        try:
            data = audio_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        # mono
        if data.ndim > 1:
            data = data.mean(axis=1)
        buffer = np.concatenate([buffer, data.astype(np.float32).flatten()])

        while len(buffer) >= chunk_samples:
            chunk = buffer[:chunk_samples]
            buffer = buffer[chunk_samples:]
            t_offset = time.time() - t0 - CHUNK_SECONDS
            transcribe_chunk(chunk, t_offset)


# ============ Shutdown ============
def shutdown(signum, frame) -> None:
    global running
    print("\n🛑 Зупинка, обробка залишку буфера...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ============ Старт ============
worker = threading.Thread(target=transcribe_worker, daemon=True)
worker.start()

print(f"📝 Файл: {md_path}")
print("▶️  Транскрипція запущена. Cmd+C — зупинити.\n" + "─" * 60)

try:
    with sd.InputStream(
        device=device_idx,
        channels=1,
        samplerate=SAMPLE_RATE,
        callback=audio_callback,
        blocksize=int(SAMPLE_RATE * 0.5),
        dtype="float32",
    ):
        while running:
            time.sleep(0.1)
except Exception as e:
    print(f"❌ Помилка: {e}")
finally:
    running = False
    time.sleep(0.5)
    if len(buffer) > SAMPLE_RATE:
        transcribe_chunk(buffer, 0)
    md_file.write(f"\n---\n_Завершено: {datetime.datetime.now().strftime('%H:%M:%S')}_\n")
    md_file.close()
    print("─" * 60)
    print(f"✅ Збережено: {md_path}")
