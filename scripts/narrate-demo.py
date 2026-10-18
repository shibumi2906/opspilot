"""Generate an authorized English narration, then assemble it locally over the saved demo.

Default mode only assembles cached WAV clips. --generate explicitly enables paid TTS calls.
Credentials are read from ignored .env and never placed in commands or artifacts.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-4o-mini-tts"
VOICE = "cedar"
INSTRUCTIONS = (
    "Read only the supplied narration in clear neutral English. Sound like a calm, confident "
    "technical presenter, natural and conversational, without sales enthusiasm. "
    "Use a consistent voice and moderately brisk pace, around 155 words per minute. "
    "Pronounce OpsPilot as Ops Pilot. Pronounce MCP, API, and ID as individual letters. "
    "Do not add an introduction, commentary, music, or sound effects."
)


def run(*command: str) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:])
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("ffmpeg and ffprobe are required")
    scenes = json.loads((ROOT / "docs/assets/narration-en.json").read_text(encoding="utf-8-sig"))
    cache = ROOT / ".tools/narration"
    cache.mkdir(parents=True, exist_ok=True)
    clips = []
    measurements = []
    key = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") if args.generate else None
    with httpx.Client(timeout=90, trust_env=False) as client:
        for index, scene in enumerate(scenes):
            payload = dict(
                model=MODEL,
                voice=VOICE,
                input=scene["text"],
                instructions=INSTRUCTIONS,
                response_format="wav",
            )
            identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
            raw = cache / f"{index:02}-{identity}.wav"
            if not raw.exists():
                if not args.generate or not key:
                    raise SystemExit(
                        "Missing cached clip; --generate and a local API key are required"
                    )
                response = client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                if not response.is_success:
                    error = response.json().get("error", {})
                    raise SystemExit(
                        f"Speech API failed: HTTP {response.status_code}, code={error.get('code')}"
                    )
                if not response.content.startswith(b"RIFF"):
                    raise SystemExit("Speech endpoint did not return WAV audio")
                raw.write_bytes(response.content)
                print(f"Generated clip {index + 1}/{len(scenes)}", flush=True)
            clean = cache / f"clean-{index:02}.wav"
            run(
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(raw),
                "-af",
                "silenceremove=start_periods=1:start_threshold=-45dB",
                str(clean),
            )
            duration = float(
                run(
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(clean),
                ).strip()
            )
            slot = scene["end"] - scene["start"]
            tempo = max(1.0, duration / slot)
            if tempo > 1.2:
                raise SystemExit(
                    f"Clip {index + 1} needs adjustment: {duration:.2f}s in {slot:.2f}s"
                )
            clips.append((clean, scene["start"], tempo))
            measurements.append(
                dict(
                    scene=index + 1,
                    start=scene["start"],
                    end=scene["end"],
                    source_seconds=duration,
                    tempo=tempo,
                )
            )
            print(f"Clip {index + 1}: {duration:.2f}s, tempo {tempo:.3f}", flush=True)
    audio = cache / "mixed.wav"
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    filters = []
    for index, (path, start, tempo) in enumerate(clips):
        command += ["-i", str(path)]
        filters.append(
            f"[{index}:a]atempo={tempo:.8f},aresample=48000,"
            f"adelay={round(start * 1000)}:all=1[a{index}]"
        )
    filters.append(
        "".join(f"[a{i}]" for i in range(len(clips)))
        + f"amix=inputs={len(clips)}:normalize=0,apad,atrim=duration=158.4,"
        "loudnorm=I=-16:TP=-1.5:LRA=7[audio]"
    )
    run(
        *command,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[audio]",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
        str(audio),
    )
    output = ROOT / "docs/assets/opspilot-demo-narrated.mp4"
    run(
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(ROOT / "docs/assets/opspilot-demo.webm"),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-t",
        "158.4",
        "-metadata",
        "comment=English voice generated by OpenAI TTS; synthetic scripted demonstration.",
        str(output),
    )
    (cache / "measurements.json").write_text(
        json.dumps(
            dict(model=MODEL, voice=VOICE, scenes=measurements, output_seconds=158.4), indent=2
        )
    )
    print(f"Created {output.name}")


if __name__ == "__main__":
    main()
