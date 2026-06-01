# ElevenLabs TTS Pipeline

A tiny Python pipeline that reads a script from `input/`, generates a voiceover
with the official [ElevenLabs](https://elevenlabs.io) SDK, and saves an MP3 to
`out/` with the **same base name** as the input file.

```
tts-pipeline/
├── input/
│   └── myscript.txt      # paste your script here (any filename)
├── out/                  # generated .mp3 lands here
├── .env                  # holds your API key (gitignored)
├── .env.example
├── requirements.txt
├── generate.py           # the main script
└── README.md
```

## Commands (quick reference)

```bash
# 1. Create & activate the virtual environment (first time only)
python3 -m venv venv && source venv/bin/activate

# 2. Install dependencies (first time, or after pulling changes)
pip install -r requirements.txt

# 3. Set up your API key (first time only)
cp .env.example .env          # then paste your key into .env

# 4. Generate the voiceover (auto-picks the single .txt in input/)
python generate.py

#    …or target a specific file in input/
python generate.py myscript.txt

# 5. Play the result
open out/myscript.mp3         # macOS  (Linux: xdg-open, Windows: start)
```

> Already set up? In a new terminal you only need:
> ```bash
> source venv/bin/activate && python generate.py
> ```

## Setup

1. **Create and activate a virtual environment** (Mac/Linux):
   ```bash
   python3 -m venv venv && source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your API key.** Copy the example env file and paste your key into `.env`:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and set:
   ```
   ELEVENLABS_API_KEY=sk_your_real_key_here
   ```
   Get a key at <https://elevenlabs.io/app/settings/api-keys>.
   `.env` is gitignored, so your key is never committed.

4. **Add your script** to `input/`, e.g. `input/myscript.txt` (UTF-8 text).

## Run it

```bash
python generate.py
```
…auto-picks the single `.txt` in `input/`, or target a specific file:
```bash
python generate.py myscript.txt
```

The MP3 appears in `out/` with the same name — e.g. `input/myscript.txt` →
`out/myscript.mp3`. If that file already exists, it's overwritten (with a note).

### Example output

```
Input:  input/myscript.txt
Output: out/myscript.mp3
Model:  eleven_flash_v2_5
Characters: 182
Estimated cost: ~91 credits (at 0.5 credits/char)
Resolving premade voice 'Liam' by name...
  matched 'Liam - Energetic, Social Media Creator' -> TX3LPaxmHKxFdv7VOQHJ
Generating audio (mp3_44100_128)...
Saved out/myscript.mp3 (mp3_44100_128).
Done.
```

## Voice & model

- **Voice** defaults to the premade voice **"Liam"** (young American male,
  energetic), resolved by name via the voices API. The lookup is restricted to
  `category="premade"` because the **free tier cannot use shared/library voices**
  (those return HTTP 402). To pin any specific voice, set `VOICE_ID` in `.env`
  and it's used directly (no lookup).
- **Model** defaults to `eleven_flash_v2_5` — the cheapest option (~0.5 credits/char),
  which roughly **doubles** your free-tier mileage vs. `eleven_multilingual_v2`.
  Change it at the top of [generate.py](generate.py) or via the `MODEL_ID` env var.
- **Speed** defaults to `1.0` (normal). Set the `SPEED` env var to go slower
  (`<1.0`) or faster (`>1.0`); ElevenLabs accepts `0.7`–`1.2` and out-of-range
  values are clamped. Example: `SPEED=1.1 python generate.py`.

## Free-tier notes

- Before generating, the script prints the **character count** and an
  **estimated credit cost** so you know what you're spending.
- Output starts at `mp3_44100_128`. If the API rejects that format, it
  automatically falls back to the lowest tier (`mp3_22050_32`) and tells you.
- Quota / `401` / `429` errors are reported as plain-English messages rather
  than raw stack traces.

## Security

- The API key is read from the `ELEVENLABS_API_KEY` environment variable via
  `python-dotenv`. It is **never** hardcoded.
- `.env` and generated `out/*.mp3` files are gitignored.
