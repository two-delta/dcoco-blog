# DCOCO blog

Project page for [DCOCO: Contextual Correction of Parallel Drafts for Speculative Decoding](https://arxiv.org/abs/2610.12570),
published at **https://two-delta.github.io/dcoco-blog/**. Code and drafters live in
[two-delta/DCOCO](https://github.com/two-delta/DCOCO).

`site/` is the whole site: one self-contained `index.html` plus its figures and media. Every push to
`main` deploys it through `.github/workflows/pages.yml`. The repository is public, and so is the site.

## Preview

```bash
python3 -m http.server 8000 --directory site
```

## The speed-comparison clip

`video/render_video.py` renders `site/media/dcoco-speed-comparison.{mp4,gif}` and its poster frame
with `rsvg-convert` and `ffmpeg`, using the Roboto files in `video/fonts/`:

```bash
uv run --no-project video/render_video.py
```

Each column's typing time is inversely proportional to the throughput the paper reports for that
method on LiveCodeBench, Llama-3.1-8B, thinking off, T=0, concurrency 1 (Table 10). Only the overall
time scale is a choice. The typed code is an illustrative HumanEval/32 solution, not a timed run.

## Figures

`site/figures/{coverage,method,concurrency}.png` are Figures 1, 2 and 3 of the arXiv v1 PDF, rendered
from its vector graphics at 240–260 dpi.
