#!/usr/bin/env python3
"""Portable local media helpers. No network access, generation API or credits."""
import argparse
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def fail(message):
    raise ValueError(message)

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write_new(path, content):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f:
        f.write(content)

def run(args):
    result = subprocess.run(args, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=1800)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:] or result.stdout[-5000:])
    return result.stdout

def require_media_tools():
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            fail(f"{name} is required on PATH for media operations.")

def probe(path):
    require_media_tools()
    p = Path(path).resolve()
    if not p.is_file():
        fail(f"Media not found: {p}")
    return json.loads(run(["ffprobe", "-v", "error", "-show_format",
                          "-show_streams", "-of", "json", str(p)]))

def length(info, kind):
    stream = next((s for s in info["streams"] if s.get("codec_type") == kind), None)
    if stream is None:
        fail(f"Missing {kind} stream")
    raw = stream.get("duration", info.get("format", {}).get("duration"))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        fail("Cannot establish media duration")
    if not math.isfinite(value) or value <= 0:
        fail("Invalid media duration")
    return value

def number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{label}: expected a number")
    if not math.isfinite(value) or value < minimum:
        fail(f"{label}: invalid range")
    return float(value)

def integer(value, label, minimum=1):
    number(value, label, minimum)
    if not isinstance(value, int):
        fail(f"{label}: expected integer")
    return value

def resolve_media(base, value):
    if not isinstance(value, str) or not value:
        fail("Each media file must have a nonempty path")
    p = Path(value).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()

def check(plan_path):
    plan_path = Path(plan_path).resolve()
    p = load(plan_path)
    if p.get("schema_version") != 1:
        fail("Unsupported schema_version")
    width = integer(p.get("width"), "width", 2)
    height = integer(p.get("height"), "height", 2)
    fps = integer(p.get("fps"), "fps")
    if width % 2 or height % 2 or width > 7680 or height > 7680 or fps > 120:
        fail("Use even dimensions <=7680 and fps <=120")
    fit = p.get("fit", "contain")
    if fit not in ("contain", "cover"):
        fail("fit must be contain or cover")
    clips = p.get("clips")
    if not isinstance(clips, list) or not clips or len(clips) > 200:
        fail("Provide 1..200 clips")
    normalized = []
    total = 0
    cache = {}
    for i, c in enumerate(clips):
        if c.get("transition"):
            fail("Precompose and review transitions externally; this renderer only joins clips.")
        file = resolve_media(plan_path.parent, c.get("file"))
        start = number(c.get("in", 0), f"clip {i}: in")
        frames = integer(c.get("frames"), f"clip {i}: frames")
        speed = number(c.get("speed", 1), f"clip {i}: speed", .25)
        if speed > 4:
            fail("speed must be <=4; choose it explicitly and review motion")
        if file not in cache:
            cache[file] = probe(file)
        duration = length(cache[file], "video")
        source_end = start + frames / fps * speed
        if start >= duration or source_end > duration + .02:
            fail(f"Clip {i} requests {source_end:.3f}s from a {duration:.3f}s source")
        normalized.append(dict(c, path=str(file), start=start, frames=frames,
                               speed=speed, source_end=source_end))
        total += frames
    music = p.get("music")
    if music:
        file = resolve_media(plan_path.parent, music.get("file"))
        start = number(music.get("in", 0), "music in")
        duration = length(probe(file), "audio")
        gain = music.get("gain_db", 0)
        if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not math.isfinite(gain):
            fail("gain_db must be finite")
        if not -60 <= gain <= 24:
            fail("gain_db must be between -60 and 24")
        fade = number(music.get("fade_out_seconds", 0), "fade_out_seconds")
        allow_silence = music.get("allow_silence", False)
        if not isinstance(allow_silence, bool):
            fail("allow_silence must be a boolean")
        if start >= duration:
            fail("Music start lies outside source")
        if fade > total / fps:
            fail("Fade cannot exceed film duration")
        if duration - start + .02 < total / fps and not allow_silence:
            fail("Music is shorter than film; shorten edit or explicitly authorize silence")
        music = dict(music, path=str(file), start=start, gain_db=gain,
                     fade_out_seconds=fade, allow_silence=allow_silence)
    return dict(p, width=width, height=height, fps=fps, fit=fit,
                clips=normalized, music=music, total_frames=total, seconds=total / fps)

def init_project(directory, title):
    dest = Path(directory).resolve()
    if dest.exists() and any(dest.iterdir()):
        fail("Choose an empty project directory; existing files will not be overwritten")
    dest.mkdir(parents=True, exist_ok=True)
    for sub in ("media", "prompts", "review", "output"):
        (dest / sub).mkdir(exist_ok=True)
    brief = load(ROOT / "assets" / "brief-template.json")
    brief["title"] = title
    write_new(dest / "brief.json", json.dumps(brief, ensure_ascii=False, indent=2))
    shutil.copyfile(ROOT / "assets" / "edit-plan.example.json", dest / "edit-plan.example.json")
    return {"project": str(dest), "status": "empty_project_created",
            "note": "Example media paths must be replaced with your actual files."}

STYLE = """body{background:#f5f2eb;color:#24342f;font:16px/1.8 system-ui;
max-width:1140px;margin:32px auto;padding:20px}h1{line-height:1.25}
section{background:#fff;padding:24px;margin:20px 0;border-radius:12px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.8 system-ui}
button{padding:10px 16px;background:#263e33;color:white;border:0;border-radius:7px;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
figure{margin:0}img{width:100%;height:auto}small{color:#54655c}"""
def page(title, body):
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style>'
            f'<h1>{html.escape(title)}</h1>{body}</html>')

def contact(source, out, step, start, end, max_frames):
    info = probe(source)
    duration = length(info, "video")
    stop = min(duration, end if end is not None else duration)
    if not math.isfinite(step) or step <= 0 or start < 0 or start >= stop:
        fail("Invalid sample range or step")
    count = math.ceil((stop - start) / step)
    if count > max_frames:
        fail(f"{count} frames requested; increase step or set a larger --max-frames")
    dest = Path(out).resolve()
    if dest.exists() and any(dest.iterdir()):
        fail("Contact directory must be empty")
    dest.mkdir(parents=True, exist_ok=True)
    cards = []
    samples = []
    for i in range(count):
        t = start + i * step
        file = dest / f"frame-{i:04d}.jpg"
        run(["ffmpeg", "-v", "error", "-n", "-i", str(Path(source).resolve()),
             "-ss", f"{t:.6f}", "-frames:v", "1", "-vf", "scale=640:-2",
             "-q:v", "3", str(file)])
        if not file.exists() or file.stat().st_size == 0:
            fail(f"No frame decoded at {t:.6f}s; inspect source timestamps")
        samples.append({"file": file.name, "source_time": round(t, 6)})
        cards.append(f'<figure><img src="{file.name}"><figcaption>{t:.3f}s</figcaption></figure>')
    body = ('<p>这是时间点抽帧，不是实时播放或试听。关键接触和接缝另查连续帧。</p>'
            '<div class="grid">' + "".join(cards) + "</div>")
    write_new(dest / "index.html", page("素材审看片", body))
    write_new(dest / "samples.json", json.dumps(samples, indent=2))
    return {"page": str(dest / "index.html"), "frames": count, "audio_heard": False}

def board(brief_path, out):
    b = load(brief_path)
    esc = lambda x: html.escape(str(x))
    body = f'<section><h2>创意</h2><p>{esc(b.get("idea",""))}</p>'
    body += '<p>本页是制作方案；各段是否生成、是否审查，以段内状态为准。</p>'
    body += '<h3>必须保留</h3><pre>' + esc(json.dumps(b.get("must_keep", []), ensure_ascii=False)) + '</pre>'
    body += '<h3>必须排除</h3><pre>' + esc(json.dumps(b.get("must_exclude", []), ensure_ascii=False)) + '</pre>'
    body += '<h3>素材</h3><pre>' + esc(json.dumps(b.get("assets", []), ensure_ascii=False, indent=2)) + '</pre></section>'
    units = b.get("units", [])
    if not units:
        body += '<section>尚未填写生成单元。先设计镜头，不自动填造提示词。</section>'
    for i, unit in enumerate(units):
        body += f'<section><h2>{esc(unit.get("id", i+1))} · {esc(unit.get("title",""))}</h2>'
        body += f'<p>状态：{esc(unit.get("status","planned"))}；时长：{esc(unit.get("seconds","未定"))}</p>'
        body += '<pre>' + esc(json.dumps(unit.get("references", []), ensure_ascii=False, indent=2)) + '</pre>'
        for lang in ("prompt_zh", "prompt_en"):
            if unit.get(lang):
                ident = f"prompt-{i}-{lang}"
                body += f'<button data-copy="{ident}">复制{esc(lang)}</button><pre id="{ident}">{esc(unit[lang])}</pre>'
        body += '</section>'
    body += """<script>
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{
 const t=document.getElementById(b.dataset.copy).textContent;
 try{await navigator.clipboard.writeText(t);b.textContent='已复制';}
 catch(e){const a=document.createElement('textarea');a.value=t;document.body.append(a);
 a.select();const ok=document.execCommand('copy');a.remove();b.textContent=ok?'已复制':'请手动选择正文复制';}
}));
</script>"""
    write_new(out, page(b.get("title", "短片制作方案"), body))
    return {"page": str(Path(out).resolve()), "units": len(units), "video_generated": False}

def render(plan_path, output):
    p = check(plan_path)
    out = Path(output).resolve()
    if out.exists():
        fail("Output already exists; use a new versioned filename")
    if out.suffix.lower() != ".mp4":
        fail("Output extension must be .mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    report = out.with_suffix(".checks.json")
    if report.exists():
        fail("Check report exists; use a new versioned output")
    w, h, fps = p["width"], p["height"], p["fps"]
    with tempfile.TemporaryDirectory(prefix="filmkit-", dir=out.parent) as temp:
        temp = Path(temp)
        segments = []
        for i, c in enumerate(p["clips"]):
            part = temp / f"part-{i:04d}.mp4"
            size = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2" if p["fit"] == "contain"
                    else f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
            vf = (f"trim=start={c['start']}:end={c['source_end']},"
                  f"setpts=(PTS-STARTPTS)/{c['speed']},fps={fps},{size},setsar=1")
            run(["ffmpeg", "-v", "error", "-n", "-i", c["path"], "-an",
                 "-vf", vf, "-frames:v", str(c["frames"]), "-c:v", "libx264",
                 "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                 "-video_track_timescale", str(fps * 1000), str(part)])
            actual = probe(part)
            n = int(next(s["nb_frames"] for s in actual["streams"] if s["codec_type"] == "video"))
            if n != c["frames"]:
                fail(f"Segment {i}: expected {c['frames']} frames, got {n}; inspect timestamps")
            segments.append(part)
        listing = temp / "concat.txt"
        # FFmpeg concat format quoting, not shell quoting; subprocess uses argument arrays.
        listing.write_text("".join("file '" + x.as_posix().replace("'", "'\\''") + "'\n"
                                   for x in segments), encoding="utf-8")
        picture = temp / "picture.mp4"
        run(["ffmpeg", "-v", "error", "-n", "-f", "concat", "-safe", "0",
             "-i", str(listing), "-c", "copy", str(picture)])
        final_temp = temp / "final.mp4"
        if p["music"]:
            m = p["music"]
            af = f"atrim=start={m['start']},asetpts=PTS-STARTPTS"
            if m["gain_db"]:
                af += f",volume={m['gain_db']}dB"
            if m["allow_silence"]:
                af += ",apad"
            af += f",atrim=duration={p['seconds']}"
            fade = m["fade_out_seconds"]
            if fade:
                af += f",afade=t=out:st={p['seconds']-fade}:d={fade}"
            run(["ffmpeg", "-v", "error", "-n", "-i", str(picture), "-i", m["path"],
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", af,
                 "-c:a", "aac", "-b:a", "192k", "-t", str(p["seconds"]),
                 "-movflags", "+faststart", str(final_temp)])
        else:
            run(["ffmpeg", "-v", "error", "-n", "-i", str(picture), "-c", "copy",
                 "-movflags", "+faststart", str(final_temp)])
        info = probe(final_temp)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        if int(video["nb_frames"]) != p["total_frames"]:
            fail("Final frame count mismatch")
        if abs(length(info, "video") - p["seconds"]) > 1/fps:
            fail("Final duration mismatch")
        if p["music"] and not any(s["codec_type"] == "audio" for s in info["streams"]):
            fail("Missing output audio")
        run(["ffmpeg", "-v", "error", "-i", str(final_temp), "-f", "null", "-"])
        # Open exclusive before copy; never overwrite an existing user file.
        with final_temp.open("rb") as src, out.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    result = {"file": str(out), "frames": p["total_frames"], "duration": p["seconds"],
              "width": w, "height": h, "fps": fps, "decode_check": "passed",
              "audio": "AAC re-encoded from selected music" if p["music"] else "none",
              "source_clip_audio": "omitted",
              "visual_review": "pending", "audio_listening": "not performed",
              "transition_processing": "none; precompose transitions separately"}
    write_new(report, json.dumps(result, ensure_ascii=False, indent=2))
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("init"); s.add_argument("directory"); s.add_argument("--title", default="我的回忆短片")
    s = sub.add_parser("probe"); s.add_argument("file")
    s = sub.add_parser("contact"); s.add_argument("file"); s.add_argument("--out", required=True)
    s.add_argument("--step", type=float, default=1); s.add_argument("--start", type=float, default=0)
    s.add_argument("--end", type=float); s.add_argument("--max-frames", type=int, default=80)
    s = sub.add_parser("board"); s.add_argument("brief"); s.add_argument("--out", required=True)
    s = sub.add_parser("check"); s.add_argument("plan")
    s = sub.add_parser("render"); s.add_argument("plan"); s.add_argument("--out", required=True)
    a = parser.parse_args()
    try:
        if a.command == "init": result = init_project(a.directory, a.title)
        elif a.command == "probe": result = probe(a.file)
        elif a.command == "contact": result = contact(a.file, a.out, a.step, a.start, a.end, a.max_frames)
        elif a.command == "board": result = board(a.brief, a.out)
        elif a.command == "check":
            p = check(a.plan); result = {"valid": True, "clips": len(p["clips"]),
                "frames": p["total_frames"], "seconds": p["seconds"],
                "warning": "Technical validation only; no visual or auditory approval."}
        else: result = render(a.plan, a.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
