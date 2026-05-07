#!/usr/bin/env python3
"""
meet_transcribe.py — локальна транскрипція Google Meet українською в реальному часі.

Стек:
    BlackHole (системне аудіо) + мікрофон → два окремих потоки sounddevice
    → faster-whisper (large-v3-turbo) → live вивід у терміналі + markdown файл

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
import yaml
from faster_whisper import WhisperModel

# ============ Конфігурація ============
_cfg: dict = {}
_config_path = Path(__file__).parent / "config.yaml"
if _config_path.exists():
    _cfg = yaml.safe_load(_config_path.read_text(encoding="utf-8")) or {}

MODEL_NAME = _cfg.get("model", "large-v3-turbo")
FALLBACK_MODEL = "large-v3-turbo"
LANGUAGE = "uk"
COMPUTE_TYPE = _cfg.get("compute_type", "int8")
SAMPLE_RATE = 16000
CHUNK_SECONDS = int(_cfg.get("chunk_seconds", 6))
SILENCE_RMS = float(_cfg.get("silence_rms", 0.003))
BEAM_SIZE = 5

BLACKHOLE_KEYWORD = _cfg.get("blackhole_keyword", "BlackHole")
MIC_PRIORITY: list[str] = _cfg.get("mic_priority", ["AirPods", "BRIO 305", "MacBook Pro Microphone"])
MIC_CHECK_INTERVAL = 2.0

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


def find_device(keyword: str) -> tuple[int, dict] | None:
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if keyword.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            return i, dev
    return None


def find_best_mic() -> tuple[int, dict] | None:
    for keyword in MIC_PRIORITY:
        result = find_device(keyword)
        if result:
            return result
    return None


def load_model() -> WhisperModel:
    print(f"📦 Завантаження моделі: {MODEL_NAME}")
    try:
        return WhisperModel(MODEL_NAME, device="auto", compute_type=COMPUTE_TYPE)
    except Exception as e:
        print(f"⚠️  Не вдалося завантажити {MODEL_NAME}: {e}")
        print(f"📦 Fallback на: {FALLBACK_MODEL}")
        return WhisperModel(FALLBACK_MODEL, device="auto", compute_type=COMPUTE_TYPE)


# ============ Стан ============
blackhole = find_device(BLACKHOLE_KEYWORD)
if not blackhole:
    print(f"❌ BlackHole не знайдено. Встанови blackhole-2ch.")
    sys.exit(1)

blackhole_idx, blackhole_info = blackhole
print(f"🔊 BlackHole: {blackhole_info['name']} (idx={blackhole_idx})")

mic = find_best_mic()
if mic:
    print(f"🎙  Мікрофон: {mic[1]['name']} (idx={mic[0]})")
else:
    print("⚠️  Мікрофон не знайдено, буде записано лише звук мітингу")

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
def make_callback(label: str):
    def audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
        if status and "input overflow" not in str(status).lower():
            pass  # PortAudio disconnection errors (-50 etc.) — ігноруємо
        mono = indata.mean(axis=1) if indata.ndim > 1 and indata.shape[1] > 1 else indata.flatten()
        audio_queue.put(mono.copy())
    return audio_callback


def open_stream(device_idx: int, label: str) -> sd.InputStream:
    n_channels = sd.query_devices(device_idx)["max_input_channels"]
    stream = sd.InputStream(
        device=device_idx,
        channels=n_channels,
        samplerate=SAMPLE_RATE,
        callback=make_callback(label),
        blocksize=int(SAMPLE_RATE * 0.5),
        dtype="float32",
    )
    stream.start()
    return stream


# ============ Mic watchdog ============
def mic_watchdog() -> None:
    current_stream: sd.InputStream | None = None
    current_idx: int | None = None

    while running:
        result = find_best_mic()

        if current_stream is not None and not current_stream.active:
            current_stream = None
            current_idx = None

        if result:
            idx, info = result
            if idx != current_idx:
                if current_stream:
                    try:
                        current_stream.stop()
                        current_stream.close()
                    except Exception:
                        pass
                try:
                    current_stream = open_stream(idx, "mic")
                    current_idx = idx
                    print(f"🎙  Мікрофон: {info['name']}")
                except Exception as e:
                    print(f"⚠️  Не вдалося відкрити мікрофон {info['name']}: {e}")
                    current_stream = None
                    current_idx = None
        else:
            if current_stream is not None:
                try:
                    current_stream.stop()
                    current_stream.close()
                except Exception:
                    pass
                current_stream = None
                current_idx = None
                print("⚠️  Мікрофон відключено, записується лише звук мітингу")

        time.sleep(MIC_CHECK_INTERVAL)

    if current_stream:
        try:
            current_stream.stop()
            current_stream.close()
        except Exception:
            pass


# ============ Транскрипція ============
def transcribe_chunk(audio: np.ndarray, t_offset_s: float) -> None:
    if len(audio) < SAMPLE_RATE:
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
        condition_on_previous_text=False,
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

watchdog = threading.Thread(target=mic_watchdog, daemon=True)
watchdog.start()

print(f"📝 Файл: {md_path}")
print("▶️  Транскрипція запущена. Cmd+C — зупинити.\n" + "─" * 60)

try:
    bh_stream = open_stream(blackhole_idx, "blackhole")
    while running:
        time.sleep(0.1)
    bh_stream.stop()
    bh_stream.close()
except Exception as e:
    print(f"❌ Помилка BlackHole: {e}")
finally:
    running = False
    time.sleep(0.5)
    if len(buffer) > SAMPLE_RATE:
        transcribe_chunk(buffer, 0)
    md_file.write(f"\n---\n_Завершено: {datetime.datetime.now().strftime('%H:%M:%S')}_\n")
    md_file.close()
    print("─" * 60)
    print(f"✅ Збережено: {md_path}")
