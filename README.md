# Flowframes + TikTok 60FPS Studio

Two **fully independent** video engines in one black-matte Windows app.

| | AI Frame Interpolation | TikTok 60FPS Patch |
|---|---|---|
| What it does | Generates *new* frames with RIFE (30→60, 60→120…) | Rewrites MP4 timing (60 FPS → 30 FPS, 2× longer) |
| Re-encodes video? | Yes (new frames must be encoded) | **Never** – every video sample stays bit-identical |
| Engine | `rife-ncnn-vulkan` (NVIDIA / AMD / Intel via Vulkan) | Native Python ISO-BMFF parser/patcher |

**Made by Mords · TikTok: @Mords_69**

## Build the Windows .exe with GitHub (no installation on your PC)

1. Create a new GitHub repository and upload **all files of this folder** (keep the `.github` folder).
2. Open the **Actions** tab → *Build Windows EXE* → **Run workflow** (it also runs on every push).
3. When it finishes (~5–10 min) open the run → **Artifacts** → download `Flowframes-TikTok60FPS-Studio-win64`.
4. Unzip and run `Flowframes-TikTok60FPS-Studio.exe`. FFmpeg, RIFE and its models are already bundled.
5. For a public download link: push a tag (`git tag v1.0.0 && git push --tags`) – the zip is attached to a GitHub Release.

> الخطوات بالعربي: ارفع كل الملفات على مستودع GitHub جديد ← تبويب **Actions** ← **Build Windows EXE** ← **Run workflow** ← بعد انتهاء البناء حمّل الملف من **Artifacts** وفك الضغط وشغّل الـ exe.

## Run from source

```
pip install -r requirements.txt
python main.py
```
Needs `ffmpeg.exe` / `ffprobe.exe` in `bin/` (or on PATH) and `rife-ncnn-vulkan` in `models/` (see `docs/MODELS.md`).
Python 3.10–3.13. The GitHub workflow uses 3.12.

## Project layout

```
main.py                     entry point
gui/                        CustomTkinter UI (dashboard, 2 workspaces, completion, about, settings)
engines/interpolation/      RIFE pipeline (independent engine #1)
engines/mp4_patch/          native MP4 patcher (independent engine #2)
core/                       shared: ffprobe analysis, hardware detection, processes, config
docs/                       algorithm, models, testing
tests/                      unit + end-to-end tests
.github/workflows/          Windows build
```
The two engines never import each other; they share only `core/`.

## Honest notes

* **Audio in the patch mode.** AAC cannot be slowed without touching the bitstream (rewriting the sample rate corrupts decoding – verified). So "Slow audio too" resamples and re-encodes *only the audio stream*; video stays untouched and is hash-verified. "Remove audio" keeps the file 100 % native. Files without audio are patched fully in place.
* The patched file with audio keeps `moov` at the end of the file (no faststart); players handle it, some web uploaders prefer moov first.
* **Backend.** Interpolation uses `rife-ncnn-vulkan` instead of PyTorch/CUDA: same RIFE models, works on any GPU vendor, and keeps the app ~250 MB instead of several GB. The engine is isolated in `engines/interpolation/`, so a PyTorch backend can be added later.
* Interpolation to non-integer targets (e.g. 24→60) interpolates to the next integer multiple (3× = 72) and FFmpeg's `fps` filter picks frames down to the target.
