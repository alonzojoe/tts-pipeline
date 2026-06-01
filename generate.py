#!/usr/bin/env python3
"""
ElevenLabs text-to-speech pipeline.

Reads a script from input/, generates a voiceover with ElevenLabs, and writes
an MP3 to out/ using the SAME base name as the input file.

Usage:
    python generate.py                # auto-pick the single .txt in input/
    python generate.py myscript.txt   # target a specific file in input/
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

# ElevenLabs raises ApiError for HTTP-level problems (401, 429, quota, etc.).
# Import path has been stable across the 2.x SDK; fall back to a bare Exception
# if the internal layout ever shifts so the script still runs.
try:
    from elevenlabs.core import ApiError
except ImportError:  # pragma: no cover - defensive
    ApiError = Exception


# --- Configuration (tweak these freely) ------------------------------------

# Default model. Flash is the cheapest (~0.5 credits/char) which roughly doubles
# the mileage of a free-tier 10k-credit/month plan vs. eleven_multilingual_v2.
# Override per-run with the MODEL_ID env var.
MODEL_ID = os.getenv("MODEL_ID", "eleven_flash_v2_5")

# Default stock voice resolved BY NAME via the voices API. We restrict the
# lookup to "premade" voices because the FREE tier cannot use shared/library
# voices (the API returns HTTP 402 paid_plan_required for those). "Liam" is a
# free premade voice that fits "young American male, upbeat / energetic".
# Override with the VOICE_ID env var to use any specific id directly.
DEFAULT_VOICE_NAME = "Liam"

# Preferred output format, with a guaranteed free-tier fallback. The 192kbps
# tiers need a paid plan, so we start at 128 and drop to the lowest mp3 if the
# API rejects it.
PRIMARY_OUTPUT_FORMAT = "mp3_44100_128"
FALLBACK_OUTPUT_FORMAT = "mp3_22050_32"

# Flash pricing is ~0.5 credits per character. Used only for the cost estimate.
CREDITS_PER_CHAR = 0.5

# Speech speed. 1.0 = normal, <1.0 slower, >1.0 faster. ElevenLabs accepts
# 0.7-1.2; values outside that are clamped (with a warning). Override per-run
# with the SPEED env var, e.g.  SPEED=1.1 python generate.py
DEFAULT_SPEED = 1.0
SPEED_MIN, SPEED_MAX = 0.7, 1.2

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("out")


def die(message: str) -> None:
    """Print a plain-English error to stderr and exit non-zero."""
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def select_input_file(arg: str | None) -> Path:
    """Resolve which .txt file to read, per the CLI rules."""
    if not INPUT_DIR.is_dir():
        die(f"input folder '{INPUT_DIR}/' does not exist. Create it and add a .txt file.")

    if arg:
        # Accept either a bare filename (resolved inside input/) or a path.
        candidate = Path(arg)
        if not candidate.exists():
            candidate = INPUT_DIR / arg
        if not candidate.exists():
            die(f"file not found: '{arg}'. Looked in '{arg}' and '{INPUT_DIR / arg}'.")
        if candidate.suffix.lower() != ".txt":
            die(f"'{candidate}' is not a .txt file.")
        return candidate

    # No argument: auto-pick the single .txt in input/.
    txt_files = sorted(p for p in INPUT_DIR.glob("*.txt") if p.is_file())
    if not txt_files:
        die(f"no .txt file found in '{INPUT_DIR}/'. Add your script there and retry.")
    if len(txt_files) > 1:
        names = ", ".join(p.name for p in txt_files)
        die(
            f"multiple .txt files in '{INPUT_DIR}/' ({names}). "
            "Pass the one you want, e.g.  python generate.py myscript.txt"
        )
    return txt_files[0]


def read_script(path: Path) -> str:
    """Read the full UTF-8 text, erroring out if it is empty."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        die(f"'{path}' is empty. Put some text in it and retry.")
    return text


def resolve_voice_id(client: ElevenLabs) -> str:
    """Return VOICE_ID from env if set, else look up DEFAULT_VOICE_NAME by name."""
    override = os.getenv("VOICE_ID", "").strip()
    if override:
        print(f"Using VOICE_ID from env: {override}")
        return override

    print(f"Resolving premade voice '{DEFAULT_VOICE_NAME}' by name...")
    # category='premade' keeps us to voices the free tier is allowed to use.
    response = client.voices.search(search=DEFAULT_VOICE_NAME, category="premade")
    voices = getattr(response, "voices", []) or []

    # Premade names carry a descriptor, e.g. "Liam - Energetic, Social Media
    # Creator", so match on the leading name rather than requiring an exact equal.
    target = DEFAULT_VOICE_NAME.lower()
    for voice in voices:
        name = (voice.name or "").lower()
        if name == target or name.startswith(target + " ") or name.split(" -")[0].strip() == target:
            print(f"  matched '{voice.name}' -> {voice.voice_id}")
            return voice.voice_id

    if voices:
        first = voices[0]
        print(
            f"  no exact match for '{DEFAULT_VOICE_NAME}'; using closest premade "
            f"result '{first.name}' -> {first.voice_id}"
        )
        return first.voice_id

    die(
        f"could not find a premade voice named '{DEFAULT_VOICE_NAME}'. "
        "Set VOICE_ID in .env to a specific voice id instead."
    )


def resolve_speed() -> float:
    """Read SPEED from env (default DEFAULT_SPEED), clamped to the allowed range."""
    raw = os.getenv("SPEED", "").strip()
    if not raw:
        return DEFAULT_SPEED
    try:
        speed = float(raw)
    except ValueError:
        print(f"  SPEED='{raw}' is not a number; using default {DEFAULT_SPEED}.")
        return DEFAULT_SPEED
    if speed < SPEED_MIN or speed > SPEED_MAX:
        clamped = max(SPEED_MIN, min(SPEED_MAX, speed))
        print(f"  SPEED={speed} is outside {SPEED_MIN}-{SPEED_MAX}; clamping to {clamped}.")
        return clamped
    return speed


def synthesize(client: ElevenLabs, voice_id: str, text: str, output_format: str, speed: float):
    """Call the TTS API; returns a stream of audio byte chunks."""
    return client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        output_format=output_format,
        voice_settings=VoiceSettings(speed=speed),
    )


def write_audio(audio_stream, out_path: Path) -> None:
    """Write the streamed audio chunks to disk."""
    with open(out_path, "wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)


def explain_api_error(err: Exception) -> str:
    """Turn an ElevenLabs/HTTP error into a plain-English message."""
    status = getattr(err, "status_code", None)
    body = getattr(err, "body", None)
    detail = ""
    if isinstance(body, dict):
        detail = str(body.get("detail", body))
    elif body:
        detail = str(body)

    code = body.get("code") if isinstance(body, dict) else None
    if status == 401:
        return (
            "authentication failed (401). Your ELEVENLABS_API_KEY looks missing "
            "or invalid. Check the key in your .env file."
        )
    if status == 402 or code in ("paid_plan_required", "payment_required"):
        return (
            "this requires a paid plan (402). Most likely the chosen voice is a "
            "shared/library voice that free accounts can't use. Use a premade "
            "voice (the default 'Liam' is free), or set VOICE_ID in .env to a "
            f"premade voice id. Details: {detail}"
        )
    if status == 429:
        return (
            "rate limit / quota exceeded (429). You've likely run out of free-tier "
            "credits for the month, or sent requests too quickly. Wait and retry, "
            f"or check your usage at elevenlabs.io. Details: {detail}"
        )
    if detail and "quota" in detail.lower():
        return f"out of credits / quota exceeded. Details: {detail}"
    if status:
        return f"the API returned an error (HTTP {status}). Details: {detail or err}"
    return f"could not reach ElevenLabs: {err}"


def main() -> None:
    load_dotenv()

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        die(
            "ELEVENLABS_API_KEY is not set. Copy .env.example to .env and paste "
            "your key:  cp .env.example .env"
        )

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    input_path = select_input_file(arg)
    text = read_script(input_path)

    # Output keeps the SAME base name as the input, in out/.
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"{input_path.stem}.mp3"
    overwriting = out_path.exists()

    # --- Free-tier awareness: report size and estimated cost before spending. -
    speed = resolve_speed()
    char_count = len(text)
    est_credits = round(char_count * CREDITS_PER_CHAR)
    print(f"Input:  {input_path}")
    print(f"Output: {out_path}" + ("  (will OVERWRITE existing file)" if overwriting else ""))
    print(f"Model:  {MODEL_ID}")
    print(f"Speed:  {speed}")
    print(f"Characters: {char_count:,}")
    print(f"Estimated cost: ~{est_credits:,} credits (at {CREDITS_PER_CHAR} credits/char)")

    client = ElevenLabs(api_key=api_key)

    try:
        # die() raises SystemExit (not a subclass of Exception), so a genuine
        # "voice not found" exit propagates cleanly past this handler.
        voice_id = resolve_voice_id(client)
    except Exception as err:
        die(explain_api_error(err))

    # Generate, falling back to a lower output format if the API rejects ours.
    output_format = PRIMARY_OUTPUT_FORMAT
    print(f"Generating audio ({output_format})...")
    try:
        audio = synthesize(client, voice_id, text, output_format, speed)
        write_audio(audio, out_path)
    except ApiError as err:
        status = getattr(err, "status_code", None)
        # A bad/unsupported format usually comes back as a 4xx that isn't
        # auth/quota/payment — only those genuinely warrant a format retry.
        if status not in (401, 402, 429) and output_format != FALLBACK_OUTPUT_FORMAT:
            print(
                f"  format '{output_format}' was rejected; "
                f"falling back to '{FALLBACK_OUTPUT_FORMAT}'."
            )
            output_format = FALLBACK_OUTPUT_FORMAT
            try:
                audio = synthesize(client, voice_id, text, output_format, speed)
                write_audio(audio, out_path)
            except ApiError as err2:
                die(explain_api_error(err2))
        else:
            die(explain_api_error(err))
    except Exception as err:  # network errors, etc.
        die(explain_api_error(err))

    action = "Overwrote" if overwriting else "Saved"
    print(f"{action} {out_path} ({output_format}).")
    print("Done.")


if __name__ == "__main__":
    main()
