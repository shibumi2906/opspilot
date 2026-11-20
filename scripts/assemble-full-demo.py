"""Assemble the real Full recording with offline narration and English captions.

Run from this checkout after record-full-demo.mjs has completed. Private capture
state stays under .tools; only the reviewed MP4, SRT and metadata are published.
Requires local ffmpeg/ffprobe and Windows Segoe UI fonts; no network calls.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


def stamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    assert work.is_relative_to(ROOT / ".tools")
    recording = read(work / "recording.json")
    proof = read(work / "database-proof.json")
    assert recording["phase"] == "complete"
    assert not recording["authentication_recorded"]
    assert recording["approved_verified"] and recording["rejected_without_ticket"]
    assert proof["approved_ticket_delta"] == 1 and proof["rejected_ticket_delta"] == 0
    plan = read(work / "plan.json")
    ffmpeg = shutil.which("ffmpeg") or "C:/ffmpeg/bin/ffmpeg.exe"
    ffprobe = shutil.which("ffprobe") or "C:/ffmpeg/bin/ffprobe.exe"
    out = ROOT / "docs/assets/full"
    movie = out / "opspilot-full-demo-en.mp4"
    assert not movie.exists(), "Preserve existing reviewed output"
    encoded = work / "encoded"
    encoded.mkdir(exist_ok=True)
    fonts = work / "fonts"
    fonts.mkdir(exist_ok=True)
    for name in ("segoeui.ttf", "segoeuib.ttf"):
        shutil.copyfile(Path("C:/Windows/Fonts") / name, fonts / name)

    def relative(path):
        return path.relative_to(ROOT).as_posix()

    regular = relative(fonts / "segoeui.ttf")
    bold = relative(fonts / "segoeuib.ttf")
    chapters, captions, elapsed = [], [], 0
    for index, item in enumerate(plan["scenes"]):
        key, duration = item["key"], item["duration_seconds"]
        chapters.append({"key": key, "title": item["chapter"], "start_seconds": elapsed})
        title = encoded / f"{key}-title.txt"
        title.write_text(textwrap.fill(item["chapter"], 19), encoding="utf-8", newline="\n")
        points = encoded / f"{key}-points.txt"
        points.write_text(
            "\n\n".join(textwrap.fill(p, 24) for p in item["points"]),
            encoding="utf-8",
            newline="\n",
        )
        role = encoded / f"{key}-role.txt"
        role.write_text(item["role"].upper(), encoding="utf-8", newline="\n")
        args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        clip = next((s for s in recording["scenes"] if s["key"] == key), None)
        if clip:
            source = work / clip["source"]
            probe = json.loads(
                subprocess.check_output(
                    [ffprobe, "-v", "error", "-show_format", "-of", "json", str(source)]
                )
            )
            start = max(0, float(probe["format"]["duration"]) - clip["content_seconds"])
            args += ["-ss", str(start), "-i", str(source)]
            content = "[0:v]scale=1536:864,setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=2[ui]"
        else:
            args += ["-loop", "1", "-i", str(ROOT / ".tools/verification/hero-preview.png")]
            content = (
                "[0:v]scale=1536:-1,pad=1536:864:0:(oh-ih)/2:color=0x142f29,setsar=1,fps=30[ui]"
            )
        args += ["-i", str(work / "audio" / f"{key}.wav")]
        vf = (
            f"{content};color=c=0x102820:s=1920x1080:r=30:d={duration}[bg];"
            "[bg][ui]overlay=344:88:shortest=1,"
            f"drawtext=fontfile={bold}:text='OPSPILOT / FULL':"
            "x=36:y=36:fontsize=22:fontcolor=0xc1e8ce,"
            f"drawtext=fontfile={regular}:text='SYNTHETIC DATA  /  SCRIPTED MODEL':"
            "x=1150:y=37:fontsize=20:fontcolor=0xa3c7ae,"
            f"drawtext=fontfile={regular}:text='{index + 1:02} / 11':"
            "x=36:y=123:fontsize=22:fontcolor=0x95c9a6,"
            f"drawtext=fontfile={bold}:textfile={relative(title)}:x=36:y=177:fontsize=30:line_spacing=12:fontcolor=white,"
            f"drawtext=fontfile={regular}:textfile={relative(role)}:x=36:y=310:fontsize=18:fontcolor=0x94d6ad,"
            f"drawtext=fontfile={regular}:textfile={relative(points)}:x=36:y=380:fontsize=21:line_spacing=8:fontcolor=0xc3d8cb[v];"
            f"[1:a]atempo={plan['narration_tempo']},aresample=48000,adelay=300,apad,atrim=duration={duration}[a]"
        )
        segment = encoded / f"{key}.mp4"
        run(
            args
            + [
                "-filter_complex",
                vf,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(segment),
            ]
        )
        words = item["narration"].split()
        chunks = [words[i : i + 12] for i in range(0, len(words), 12)]
        spoken = item["audio_seconds"] / plan["narration_tempo"]
        consumed = 0
        for chunk in chunks:
            begin = elapsed + 0.3 + spoken * consumed / len(words)
            consumed += len(chunk)
            end = elapsed + 0.3 + spoken * consumed / len(words)
            text = "\n".join(textwrap.wrap(" ".join(chunk), 78))
            captions.append(f"{len(captions) + 1}\n{stamp(begin)} --> {stamp(end)}\n{text}\n")
        elapsed += duration
        print(f"Encoded {key}", flush=True)
    srt = out / "opspilot-full-demo-en.srt"
    srt.write_text("\n".join(captions), encoding="utf-8")
    listing = encoded / "segments.txt"
    listing.write_text(
        "\n".join(f"file '{s['key']}.mp4'" for s in plan["scenes"]), encoding="utf-8"
    )
    joined = encoded / "joined.mp4"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(joined),
        ]
    )
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(joined),
            "-i",
            str(srt),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "1:0",
            "-vf",
            f"subtitles={relative(srt)}:force_style='FontName=Segoe UI,FontSize=9,"
            "MarginV=8,Outline=1,BackColour=&H80000000,BorderStyle=3'",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-c:s",
            "mov_text",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata",
            "title=OpsPilot Full - English demonstration",
            "-movflags",
            "+faststart",
            str(movie),
        ]
    )
    probe = json.loads(
        subprocess.check_output(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(movie)]
        )
    )
    streams = probe["streams"]
    assert streams[0]["width"] == 1920 and streams[0]["height"] == 1080
    assert abs(float(probe["format"]["duration"]) - elapsed) < 0.5
    metadata = {
        "captured_on": "2026-11-20",
        "actual_application_ui": True,
        "synthetic": True,
        "model": "scripted",
        "authentication_recorded": False,
        "voice": plan["voice"],
        "speech_engine": plan["engine"],
        "narration_tempo": plan["narration_tempo"],
        "paid_calls": 0,
        "external_tts_requests": 0,
        "jira_dispatches": 0,
        "approved_local_tickets": 1,
        "rejected_runs_without_ticket": 1,
        "same_saved_action_verified": recording["same_saved_action_verified"],
        "duration_seconds": elapsed,
        "width": 1920,
        "height": 1080,
        "video_codec": "h264",
        "audio_codec": "aac",
        "language": "en",
        "captions": "burned in and embedded selectable English; separate SRT",
        "chapters": chapters,
        "sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [movie, srt, out / "demo-en-script.json"]
        },
        "scope": "Portfolio Full demo; no production or ASVS certification claim",
        "capture_recovery": (
            "Loading-label assertion stopped before approval; "
            "retained run resumed without recreating it"
        ),
    }
    (out / "demo-en-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": True, "seconds": elapsed, "bytes": movie.stat().st_size}))


if __name__ == "__main__":
    main()
