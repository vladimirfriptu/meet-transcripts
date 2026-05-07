# Meet Transcribe — локальна транскрипція Google Meet українською

Real-time транскрипція в командному рядку, повністю локально на M-series Mac.
Стек: BlackHole + faster-whisper + Yehor's Ukrainian fine-tune + IT-словник.

## Що отримаєш

- Live-вивід тексту в терміналі під час мітингу
- Markdown-файл з таймкодами в `~/Documents/MeetTranscripts/meet_YYYYMMDD_HHMMSS.md`
- Все локально, без хмари, без ботів у созвоні
- Українська мова з IT-лексикою (initial_prompt + Yehor fine-tune)

## Перший запуск (одноразово)

```bash
chmod +x setup.sh
./setup.sh
```

Скрипт встановить BlackHole, portaudio і Python-залежності.

### Вручну в Audio MIDI Setup

Відкрий **Audio MIDI Setup** (Cmd+Space → "Audio MIDI Setup").

**1. Multi-Output Device** — щоб ти чув співрозмовників:
- Натисни `+` → Create Multi-Output Device
- Постав галочки: `BlackHole 2ch` + твій вихід (навушники / динаміки)
- Назви, наприклад, "Meet Listen"

**2. Aggregate Device** — щоб скрипт записував і голос інших, і твій:
- Натисни `+` → Create Aggregate Device
- Постав галочки: `BlackHole 2ch` + `Built-in Microphone` (або твій USB-мік)
- Назви, наприклад, "Meet Record"
- В колонці Drift Correction постав галочку для одного з пристроїв (зазвичай мікрофону)

## Перед кожним мітингом

1. **System Settings → Sound → Output**: вибери `Meet Listen`
2. У Google Meet (в самому браузері) переконайся, що:
   - Microphone: твій звичайний мікрофон (не BlackHole)
   - Speaker: System default (буде Meet Listen)
3. Запусти скрипт:

```bash
source .venv/bin/activate
python meet_transcribe.py
```

4. Після мітингу — `Ctrl+C`. Файл збережеться, шлях покажеться в терміналі.
5. **Не забудь повернути Output на звичайний у System Settings.**

## Інтеграція з Notion / Claude Code

Markdown готовий до використання. Швидкий пайплайн:

```bash
# Після мітингу — згенерувати саммарі через Claude Code:
cd ~/Documents/MeetTranscripts
claude "прочитай meet_LATEST.md, зроби короткий саммарі з action items \
        і створи сторінку в Notion під 'Операційні' з посиланням на оригінал"
```

## Налаштування

В `meet_transcribe.py` зверху:

| Змінна | Значення | Коментар |
|---|---|---|
| `MODEL_NAME` | `Yehor/whisper-large-v3-turbo-quantized-uk` | UA fine-tune; fallback на large-v3-turbo |
| `COMPUTE_TYPE` | `int8` | швидкість; постав `float16` для якості |
| `CHUNK_SECONDS` | `6` | менше = швидше реакція, більше = краще контекст |
| `BEAM_SIZE` | `5` | стандартний; 1 для швидкості, 10 для якості |
| `DEVICE_KEYWORD` | `BlackHole` | заміни на `Meet Record` якщо назвав агрегат інакше |

**Словник** в `it_glossary_uk.txt` — додавай свої терміни, імена колег, назви проектів. Ліміт ~224 токенів (~150-200 слів кирилицею).

## Тонкощі

- **Гілка vs ветка**: Yehor fine-tune навчений на CV/VOA — в технічних термінах все ще може спіткатись. Словник критичний.
- **Двомовність**: якщо в созвоні переходять на російську/англійську — Whisper все одно транскрибує (з гіршою точністю), але без перекладу.
- **Ехо**: якщо чуєш себе в навушниках — Drift Correction в Aggregate Device не виставлений правильно, або в Meet вимкнено echo cancellation.
- **Приватність**: все локально. Аудіо ніколи не покидає Mac.

## Альтернативи якщо щось пішло не так

- Точність недостатня → постав `COMPUTE_TYPE = "float16"` і `MODEL_NAME = "large-v3"` (без turbo)
- Лагає на M4 Pro (малоймовірно) → `large-v3-turbo` стокова + `int8`
- Yehor модель не завантажується → скрипт автоматично переключиться на `large-v3-turbo`
- Хочеться GUI замість терміналу → MacWhisper Pro з режимом live recording (платний, ~60€)

## Файли проекту

```
meet_transcribe/
├── meet_transcribe.py    # головний скрипт
├── it_glossary_uk.txt    # IT-словник (initial_prompt)
├── requirements.txt      # Python deps
├── setup.sh              # авто-встановлення
└── README.md             # цей файл
```
