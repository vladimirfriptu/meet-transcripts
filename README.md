# Meet Transcribe — локальна транскрипція Google Meet українською

Real-time транскрипція в командному рядку, повністю локально на M-series Mac.
Стек: BlackHole + faster-whisper + IT-словник.

## Що отримаєш

- Live-вивід тексту в терміналі під час мітингу
- Markdown-файл з таймкодами в `~/Documents/MeetTranscripts/meet_YYYYMMDD_HHMMSS.md`
- Все локально, без хмари, без ботів у созвоні
- Українська мова з IT-лексикою (initial_prompt)
- Автоматичне переключення мікрофону (AirPods сіли → BRIO 305 → MacBook mic)

## Перший запуск (одноразово)

```bash
chmod +x setup.sh
./setup.sh
```

Скрипт встановить BlackHole, portaudio і Python-залежності.

### Налаштування мікрофонів (config.yaml)

Скопіюй шаблон і відредагуй під своє обладнання:

```bash
cp config.example.yaml config.yaml
```

У `config.yaml` вкажи свої мікрофони в порядку пріоритету:

```yaml
mic_priority:
  - AirPods          # перший доступний буде використано
  - BRIO 305
  - MacBook Pro Microphone
```

Переглянути назви своїх пристроїв:

```bash
source .venv/bin/activate && python -c "import sounddevice as sd; [print(f\"[{d['index']}] {d['name']}\") for d in sd.query_devices() if d['max_input_channels'] > 0]"
```

Приклад виводу:
```
[1] Vladimir's iPhone Microphone
[3] AirPods (Владимир)
[5] BRIO 305
[7] MacBook Pro Microphone
```

В `mic_priority` вкажи **підрядок** з назви — регістр не важливий. Наприклад, `AirPods` знайде `AirPods (Владимир)`.

`config.yaml` не потрапляє в git — у кожного члена команди свій.

### Вручну в Audio MIDI Setup

> **Якщо BlackHole не з'являється в списку пристроїв** після встановлення — перезапусти аудіосервіс macOS:
> ```bash
> sudo killall coreaudiod
> ```
> Після цього відкрий (або перезапусти) Audio MIDI Setup — BlackHole 2ch з'явиться.

Відкрий **Audio MIDI Setup** (Cmd+Space → "Audio MIDI Setup").

**Multi-Output Device** — щоб ти чув співрозмовників і скрипт їх записував одночасно:
- Натисни `+` → Create Multi-Output Device
- Постав галочки: `BlackHole 2ch` + твій вихід (навушники / динаміки)
- Назви, наприклад, "Meet Listen"

> Aggregate Device більше не потрібен — скрипт читає BlackHole і мікрофон напряму.

## Перед кожним мітингом

1. **System Settings → Sound → Output**: вибери `Meet Listen`
2. У Google Meet (в самому браузері) переконайся, що:
   - Microphone: твій звичайний мікрофон (не BlackHole)
   - Speaker: System default (буде Meet Listen)
3. Запусти скрипт:

```bash
just -g meet
# або вручну:
source .venv/bin/activate && python meet_transcribe.py
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

## Налаштування (config.yaml)

| Параметр | Значення за замовчуванням | Коментар |
|---|---|---|
| `mic_priority` | `[AirPods, BRIO 305, MacBook Pro Microphone]` | список мікрофонів за пріоритетом |
| `blackhole_keyword` | `BlackHole` | підрядок у назві loopback-пристрою |
| `model` | `large-v3-turbo` | модель Whisper |
| `compute_type` | `int8` | швидкість; `float16` для точності |
| `chunk_seconds` | `6` | менше = швидша реакція, більше = кращий контекст |
| `silence_rms` | `0.003` | поріг тиші; збільш при шумному оточенні |

**Словник** в `it_glossary_uk.txt` — додавай свої терміни, імена колег, назви проектів. Ліміт ~224 токенів (~150-200 слів кирилицею).

## Тонкощі

- **Двомовність**: якщо в созвоні переходять на російську/англійську — Whisper транскрибує (з гіршою точністю), але без перекладу.
- **Приватність**: все локально. Аудіо ніколи не покидає Mac.

## Альтернативи якщо щось пішло не так

- Точність недостатня → в `config.yaml` постав `compute_type: float16` і `model: large-v3`
- Лагає → `model: large-v3-turbo` + `compute_type: int8`
- Хочеться GUI замість терміналу → MacWhisper Pro з режимом live recording (платний, ~60€)

## Файли проекту

```
meet_transcribe/
├── meet_transcribe.py      # головний скрипт
├── config.example.yaml     # шаблон конфігу (комітиться)
├── config.yaml             # твій конфіг (в .gitignore)
├── it_glossary_uk.txt      # IT-словник (initial_prompt)
├── requirements.txt        # Python deps
├── setup.sh                # авто-встановлення
└── README.md               # цей файл
```
