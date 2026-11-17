# Testing

```
python -m unittest discover -s tests -v
```
* `test_timing.py` – rational timing maths.
* `test_mp4_patch.py` – generates real MP4s with FFmpeg (video-only, A/V, NTSC 59.94, B-frames), patches them, checks exact duration/FPS, bit-identical video samples, refusal to overwrite the source, rejection of garbage. Skipped if FFmpeg is missing.

Manual checklist (needs a Windows machine with a GPU): run an interpolation 30→60 on a short clip and a 3-s preview; compare the output with the source; try CPU mode; cancel mid-run (temp folder `.ff_work_*` must disappear); try a VFR phone recording; try a low-VRAM situation (large 4K clip) and confirm the GPU-memory message.
Status: the MP4 engine is tested end-to-end. The RIFE pipeline was tested with a stand-in executable (plumbing, segments, encoding, validation); the real RIFE run and the GUI still need a first run on Windows.
