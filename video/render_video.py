"""Render the DCOCO speed-comparison clip (MP4 + GIF + poster) into site/media/.

Every column types the same text; each one's duration is inversely proportional to the
throughput the paper measured for that method, so the relative pacing is the measured one and
only the overall time scale is chosen (Vanilla finishes in TYPE_SECONDS).
Run from anywhere: `uv run video/render_video.py`. Needs rsvg-convert and ffmpeg.
"""
import html
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "site" / "media"
W, H, FPS = 1280, 720, 30
TYPE_SECONDS, HOLD_SECONDS = 14.0, 3.0

# Paper Table 10: Llama-3.1-8B, thinking off, T=0, concurrency 1, LiveCodeBench row (tok/s).
LANES = [
    ("Vanilla", "no speculation", 278.7),
    ("DSpark", "semi-autoregressive drafter", 972.1),
    ("DFlash", "parallel drafter", 990.0),
    ("Domino", "sequential corrector", 1050.5),
    ("DCOCO", "parallel corrector · ours", 1448.8),
]
INK, MUTED, LINE, BG, CARD = "#0f1b2d", "#5b6b80", "#d3dceb", "#f4f7fc", "#ffffff"
BLUE, BLUE_SOFT, GOLD = "#1f5fd1", "#e7effd", "#e3a21a"
SANS, MONO = "Roboto", "'Roboto Mono', monospace"

CODE = """def find_zero(xs: list):
    left, right = -1.0, 1.0
    left_value = poly(xs, left)
    right_value = poly(xs, right)

    while left_value == 0:
        return left
    while right_value == 0:
        return right

    while (left_value < 0) == (right_value < 0):
        left *= 2
        right *= 2
        left_value = poly(xs, left)
        right_value = poly(xs, right)

    for _ in range(100):
        middle = (left + right) / 2
        middle_value = poly(xs, middle)

        if middle_value == 0:
            return middle
        if (left_value < 0) != (middle_value < 0):
            right = middle
            right_value = middle_value
        else:
            left = middle
            left_value = middle_value

    return (left + right) / 2"""
DURATIONS = [TYPE_SECONDS * LANES[0][2] / rate for _, _, rate in LANES]
FINISH_RANK = {i: r for r, i in enumerate(sorted(range(len(LANES)), key=lambda i: DURATIONS[i]))}


def text(x, y, s, size=14, fill=INK, family=SANS, weight=400, anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" xml:space="preserve">{html.escape(s)}</text>')


def wrap(code, width):
    # Continuation lines keep the source indentation so wrapped code still reads as code.
    out = []
    for line in code.split("\n"):
        indent = len(line) - len(line.lstrip())
        while len(line) > width:
            cut = line.rfind(" ", indent + 1, width + 1)
            cut = cut if cut > indent else width
            out.append(line[:cut])
            line = " " * (indent + 4) + line[cut:].lstrip()
        out.append(line)
    return out


def pop(t):
    # Ease-out-back: icons overshoot slightly as they land.
    t = max(0.0, min(1.0, t / 0.35))
    return 1 + 2.7 * (t - 1) ** 3 + 1.7 * (t - 1) ** 2 if t else 0.0


def trophy(cx, cy, s):
    return (f'<g transform="translate({cx},{cy}) scale({s})">'
            f'<path d="M-9,-11 H9 V-4 A9,9 0 0 1 -9,-4 Z" fill="{GOLD}"/>'
            f'<path d="M-9,-8 H-13 A4,5 0 0 0 -8,0 M9,-8 H13 A4,5 0 0 1 8,0" fill="none" stroke="{GOLD}" stroke-width="2.4"/>'
            f'<rect x="-2" y="4" width="4" height="5" fill="{GOLD}"/><rect x="-7" y="9" width="14" height="3.5" rx="1" fill="{GOLD}"/></g>')


def sad(cx, cy, s):
    return (f'<g transform="translate({cx},{cy}) scale({s})">'
            f'<circle r="10" fill="#dfe6f1" stroke="{MUTED}" stroke-width="1.6"/>'
            f'<circle cx="-3.5" cy="-2.5" r="1.4" fill="{MUTED}"/><circle cx="3.5" cy="-2.5" r="1.4" fill="{MUTED}"/>'
            f'<path d="M-4.5,5.5 Q0,1.5 4.5,5.5" fill="none" stroke="{MUTED}" stroke-width="1.6" stroke-linecap="round"/></g>')


def spinner(cx, cy, t, color):
    a = (t * 400) % 360
    return (f'<circle cx="{cx}" cy="{cy}" r="7" fill="none" stroke="{LINE}" stroke-width="2"/>'
            f'<path d="M{cx},{cy - 7} A7,7 0 0 1 {cx + 7},{cy}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linecap="round" transform="rotate({a:.0f} {cx} {cy})"/>')


def frame(t):
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         text(36, 40, "DCOCO", 17, INK, weight=700),
         text(108, 40, "Contextual Correction of Parallel Drafts for Speculative Decoding", 13, MUTED, weight=300),
         text(W - 36, 40, "arXiv 2610.12570", 12, MUTED, MONO, anchor="end"),
         f'<line x1="36" y1="56" x2="{W - 36}" y2="56" stroke="{LINE}"/>',
         text(36, 96, "Same answer. DCOCO gets there first.", 32, INK, weight=700),
         text(36, 120, "HumanEval/32 · identical completion in every column · pace set by each method's measured throughput", 14, MUTED, weight=300)]
    x0, y0, gap, ch = 36, 136, 10, 524
    cw = (W - 2 * x0 - gap * (len(LANES) - 1)) / len(LANES)
    for i, (name, tag, rate) in enumerate(LANES):
        x, ours, done_at = x0 + i * (cw + gap), name == "DCOCO", DURATIONS[i]
        accent = BLUE if ours else INK
        s.append(f'<rect x="{x:.1f}" y="{y0}" width="{cw:.1f}" height="{ch}" rx="8" fill="{BLUE_SOFT if ours else CARD}" '
                 f'stroke="{BLUE if ours else LINE}" stroke-width="{2.5 if ours else 1}"/>')
        s.append(text(x + 14, y0 + 28, name, 17, accent, weight=700))
        s.append(text(x + 14, y0 + 46, tag, 10.5, MUTED, MONO))
        ix, iy = x + cw - 24, y0 + 25
        if t < done_at:
            s.append(spinner(ix, iy, t, accent))
            s.append(text(ix - 14, iy + 4, "Thinking" + "." * (int(t * 3) % 4), 10.5, MUTED, MONO, anchor="end"))
        else:
            rank = FINISH_RANK[i]
            s.append((trophy if rank == 0 else sad)(ix, iy, pop(t - done_at)))
            label = ["1st", "2nd", "3rd", "4th", "5th"][rank]
            s.append(text(ix - 21, iy + 4, label, 11, GOLD if rank == 0 else MUTED, MONO, weight=700, anchor="end"))
        s.append(f'<line x1="{x + 14}" y1="{y0 + 60}" x2="{x + cw - 14}" y2="{y0 + 60}" stroke="{LINE}"/>')

        p = min(1.0, t / done_at)
        lines = wrap(CODE[:round(p * len(CODE))], 36)
        for r, line in enumerate(lines):
            s.append(text(x + 14, y0 + 80 + r * 10.8, line, 9.3, "#1d2a3d", MONO))
        if p < 1 and math.sin(t * math.tau * 1.2) > -0.3:
            r = len(lines) - 1
            s.append(f'<rect x="{x + 14 + len(lines[r]) * 5.58:.1f}" y="{y0 + 72 + r * 10.8:.1f}" width="5" height="10" fill="{accent}"/>')

        by = y0 + ch - 44
        s.append(f'<rect x="{x + 14}" y="{by}" width="{cw - 28:.1f}" height="4" rx="2" fill="{LINE}"/>')
        s.append(f'<rect x="{x + 14}" y="{by}" width="{(cw - 28) * p:.1f}" height="4" rx="2" fill="{BLUE if ours else "#7d8ca3"}"/>')
        s.append(text(x + 14, y0 + ch - 16, f"{rate:,.1f} tok/s", 14, accent, MONO, weight=700))
        s.append(text(x + cw - 14, y0 + ch - 16, f"{rate / LANES[0][2]:.2f}×", 14, accent, MONO, weight=700, anchor="end"))
    s.append(f'<line x1="36" y1="672" x2="{W - 36}" y2="672" stroke="{LINE}"/>')
    s.append(text(36, 696, "Throughput: paper Table 10 (Llama-3.1-8B, thinking off, greedy, concurrency 1, LiveCodeBench). "
                  "Illustrative sample text; not a timed HumanEval run.", 10.5, MUTED, weight=300))
    s.append(text(W - 36, 696, "DCOCO: 1.38× the runner-up", 11, BLUE, weight=700, anchor="end"))
    return "".join(s) + "</svg>"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = round((TYPE_SECONDS + HOLD_SECONDS) * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Point fontconfig at the bundled Roboto files so renders do not depend on installed fonts.
        conf = tmp / "fonts.conf"
        conf.write_text(f'<fontconfig><dir>{HERE / "fonts"}</dir><cachedir>{tmp}/fc</cachedir>'
                        '<include ignore_missing="yes">/opt/homebrew/etc/fonts/fonts.conf</include></fontconfig>')
        env = {**os.environ, "FONTCONFIG_FILE": str(conf)}
        for k in range(n):
            png = subprocess.run(["rsvg-convert"], input=frame(k / FPS).encode(), stdout=subprocess.PIPE, check=True, env=env)
            (tmp / f"f{k:05d}.png").write_bytes(png.stdout)
        frames = ["-framerate", str(FPS), "-i", str(tmp / "f%05d.png")]
        ff = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        subprocess.run(ff + frames + ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                                      "-movflags", "+faststart", "-an", str(OUT / "dcoco-speed-comparison.mp4")], check=True)
        subprocess.run(ff + frames + ["-vf", "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none",
                                      str(OUT / "dcoco-speed-comparison.gif")], check=True)
        subprocess.run(ff + ["-i", str(tmp / f"f{n - 1:05d}.png"), "-q:v", "3", str(OUT / "dcoco-speed-comparison-poster.jpg")], check=True)
    for f in sorted(OUT.glob("dcoco-speed-comparison*")):
        print(f.name, f"{f.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
