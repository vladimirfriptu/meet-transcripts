#!/usr/bin/env python3
"""
meet_record.py — запис аудіо мітингу у WAV файл.
Після мітингу запусти: just -g meet-transcribe
"""

from __future__ import annotations

import sys
import time
import signal
import threading
import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
import yaml

# ============ Конфігурація ============
_cfg: dict = {}
_config_path = Path(__file__).parent / "config.yaml"
if _config_path.exists():
    _cfg = yaml.safe_load(_config_path.read_text(encoding="utf-8")) or {}

SAMPLE_RATE = 16000
BLACKHOLE_KEYWORD = _cfg.get("blackhole_keyword", "BlackHole")
MIC_PRIORITY: list[str] = _cfg.get("mic_priority", ["AirPods", "BRIO 305", "MacBook Pro Microphone"])
MIC_CHECK_INTERVAL = 2.0

OUTPUT_DIR = Path.home() / "Documents" / "MeetTranscripts"


# ============ Device utils ============
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


# ============ Стан ============
blackhole = find_device(BLACKHOLE_KEYWORD)
if not blackhole:
    print("❌ BlackHole не знайдено.")
    sys.exit(1)

blackhole_idx, blackhole_info = blackhole
print(f"🔊 BlackHole: {blackhole_info['name']} (idx={blackhole_idx})")

mic = find_best_mic()
if mic:
    print(f"🎙  Мікрофон: {mic[1]['name']} (idx={mic[0]})")
else:
    print("⚠️  Мікрофон не знайдено, буде записано лише звук мітингу")

session_start = datetime.datetime.now()
dated_dir = OUTPUT_DIR / session_start.strftime("%Y-%m-%d")
dated_dir.mkdir(parents=True, exist_ok=True)
wav_path = dated_dir / f"meet_{session_start.strftime('%H%M%S')}.wav"

bh_chunks: list[np.ndarray] = []
mic_chunks: list[np.ndarray] = []
running = True


# ============ Audio I/O ============
def make_callback(bucket: list[np.ndarray]):
    def audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
        mono = indata.mean(axis=1) if indata.ndim > 1 and indata.shape[1] > 1 else indata.flatten()
        bucket.append(mono.copy())
    return audio_callback


def open_stream(device_idx: int, bucket: list[np.ndarray]) -> sd.InputStream:
    n_channels = sd.query_devices(device_idx)["max_input_channels"]
    stream = sd.InputStream(
        device=device_idx,
        channels=n_channels,
        samplerate=SAMPLE_RATE,
        callback=make_callback(bucket),
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
        if current_stream is not None and not current_stream.active:
            current_stream = None
            current_idx = None

        result = find_best_mic()
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
                    current_stream = open_stream(idx, mic_chunks)
                    current_idx = idx
                    print(f"\r🎙  Мікрофон: {info['name']}")
                except Exception as e:
                    print(f"\r⚠️  Не вдалося відкрити мікрофон: {e}")
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
                print("\r⚠️  Мікрофон відключено")

        time.sleep(MIC_CHECK_INTERVAL)

    if current_stream:
        try:
            current_stream.stop()
            current_stream.close()
        except Exception:
            pass


# ============ Shutdown ============
def shutdown(signum, frame) -> None:
    global running
    print("\n🛑 Зупинка запису...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ============ Старт ============
watchdog = threading.Thread(target=mic_watchdog, daemon=True)
watchdog.start()

print(f"💾 Файл: {wav_path}")
print("⏺  Запис розпочато. Cmd+C — зупинити.\n" + "─" * 60)

t0 = time.time()
try:
    bh_stream = open_stream(blackhole_idx, bh_chunks)
    while running:
        elapsed = int(time.time() - t0)
        print(f"\r⏱  {elapsed // 60:02d}:{elapsed % 60:02d}", end="", flush=True)
        time.sleep(1)
    bh_stream.stop()
    bh_stream.close()
except Exception as e:
    print(f"\n❌ Помилка BlackHole: {e}")
finally:
    running = False
    print()
    if not bh_chunks:
        print("⚠️  Нічого не записано")
        sys.exit(1)

    bh_audio = np.concatenate(bh_chunks)

    if mic_chunks:
        mic_audio = np.concatenate(mic_chunks)
        min_len = min(len(bh_audio), len(mic_audio))
        mixed = (bh_audio[:min_len] + mic_audio[:min_len]) * 0.5
    else:
        mixed = bh_audio

    sf.write(str(wav_path), mixed, SAMPLE_RATE, subtype="PCM_16")
    duration = len(mixed) / SAMPLE_RATE
    print(f"✅ Збережено: {wav_path}")
    print(f"   Тривалість: {int(duration // 60):02d}:{int(duration % 60):02d}")
    print(f"\nТранскрипція: just -g meet-transcribe")
