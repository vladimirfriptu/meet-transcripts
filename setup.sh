#!/usr/bin/env bash
# setup.sh — встановлення залежностей для meet_transcribe на macOS (Apple Silicon)

set -e

echo "▶️  Перевірка Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew не знайдено. Встанови з https://brew.sh/"
    exit 1
fi

echo "▶️  Встановлення BlackHole 2ch (віртуальний аудіо-драйвер)..."
brew install blackhole-2ch || echo "ℹ️  BlackHole вже встановлений або потребує підтвердження"

echo "▶️  Встановлення portaudio (для sounddevice)..."
brew install portaudio

echo "▶️  Створення Python venv..."
python3 -m venv .venv
source .venv/bin/activate

echo "▶️  Встановлення Python-залежностей..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Готово."
echo ""
echo "Наступні кроки (одноразово, вручну):"
echo "  1. Відкрий 'Audio MIDI Setup' (Налаштування Audio MIDI)"
echo "  2. Створи Multi-Output Device: BlackHole 2ch + твої навушники"
echo "     → це для того, щоб ти ЧУВ співрозмовників"
echo "  3. Створи Aggregate Device: BlackHole 2ch + Built-in Microphone"
echo "     → це для того, щоб скрипт ЗАПИСУВАВ і їх, і тебе"
echo ""
echo "Перед мітингом:"
echo "  • System Settings → Sound → Output: Multi-Output Device"
echo "  • Запусти: source .venv/bin/activate && python meet_transcribe.py"
echo ""
