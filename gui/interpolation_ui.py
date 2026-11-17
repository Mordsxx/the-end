"""Workspace 1 - AI Frame Interpolation (RIFE). Completely independent from the MP4 patch workspace."""
import os
import tempfile
import tkinter as tk
from fractions import Fraction
from tkinter import messagebox

import customtkinter as ctk

from core import config
from core.errors import StudioError
from core.paths import open_file
from core.process_manager import BackgroundTask
from core.video_analyzer import analyze, extract_thumbnail
from engines.interpolation import gpu_manager, model_manager, rife_engine
from engines.interpolation.frame_processor import FORMATS, RESOLUTIONS
from . import theme as T
from .common import fmt_fps, record_history, summarize_output, unique_path

MULTS = ["2x", "3x", "4x", "5x", "6x", "8x"]


class InterpolationPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.info = None
        self.task: BackgroundTask | None = None
        self._exact_target: Fraction | None = None
        self._thumb = None
        self._sync_lock = False
        self._build()

    # ------------------------------------------------------------------------------------------ UI
    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        T.label(head, "AI Frame Interpolation", 24, "bold").pack(anchor="w")
        T.label(head, "Generate genuinely new frames with RIFE — smoother motion at higher FPS.", 13, "normal", T.MUTED).pack(anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="c")
        body.columnconfigure(1, weight=4, uniform="c")

        left = T.card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_in = ctk.CTkFrame(left, fg_color="transparent")
        left_in.pack(fill="both", expand=True, padx=18, pady=16)
        left_in.columnconfigure(0, weight=1)

        # input
        def mk_input(p):
            row = ctk.CTkFrame(p, fg_color="transparent"); row.pack(fill="x")
            self.in_var = tk.StringVar()
            e = T.entry(row, self.in_var, "Choose a video…", width=10); e.pack(side="left", fill="x", expand=True)
            e.configure(state="readonly")
            T.ghost_button(row, "Browse", self._pick_input, width=90).pack(side="left", padx=(8, 0))
        T.field(left_in, 0, "Input video", mk_input)

        self.grid_info = T.InfoGrid(left_in)
        self.grid_info.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.grid_info.clear()

        # fps
        fps_row = ctk.CTkFrame(left_in, fg_color="transparent")
        fps_row.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for i in range(3):
            fps_row.columnconfigure(i, weight=1, uniform="f")
        self.orig_var, self.target_var, self.mult_var = tk.StringVar(value="—"), tk.StringVar(), tk.StringVar(value="2x")
        for i, (cap, w) in enumerate([("Original FPS", lambda p: _ro(p, self.orig_var)),
                                      ("Target FPS", lambda p: _tgt(p, self.target_var, self._on_target_typed)),
                                      ("Multiplier", lambda p: T.option_menu(p, MULTS, self.mult_var, self._on_mult, width=10))]):
            box = ctk.CTkFrame(fps_row, fg_color="transparent")
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            T.heading(box, cap.upper()).pack(anchor="w", pady=(0, 4))
            w(box).pack(fill="x")

        # model / device
        models = model_manager.list_models()
        self._models = {m.label: m for m in models}
        labels = list(self._models) or ["No RIFE model found — see Settings"]
        self.model_var = tk.StringVar(value=labels[0])
        T.field(left_in, 3, "AI model", lambda p: _pack(T.option_menu(p, labels, self.model_var, width=10)))
        self._dev = dict(gpu_manager.device_choices())
        self.dev_var = tk.StringVar(value=next(iter(self._dev)))
        T.field(left_in, 4, "Processing device", lambda p: _pack(T.option_menu(p, list(self._dev), self.dev_var, width=10)))

        self.preset_var = tk.StringVar(value="Balanced")
        T.field(left_in, 5, "Quality preset (Fast · Balanced · High Quality)",
                lambda p: _pack(T.segmented(p, ["Fast", "Balanced", "High Quality"], self.preset_var)))

        row = ctk.CTkFrame(left_in, fg_color="transparent")
        row.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        for i in range(3):
            row.columnconfigure(i, weight=1, uniform="g")
        self.res_var, self.fmt_var, self.batch_var = tk.StringVar(value="Original"), tk.StringVar(value="MP4 · H.264"), tk.StringVar(value="160")
        for i, (cap, w) in enumerate([("Output resolution", lambda p: T.option_menu(p, list(RESOLUTIONS), self.res_var, width=10)),
                                      ("Output format", lambda p: T.option_menu(p, list(FORMATS), self.fmt_var, width=10)),
                                      ("Batch (frames)", lambda p: T.entry(p, self.batch_var, width=10))]):
            box = ctk.CTkFrame(row, fg_color="transparent")
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            T.heading(box, cap.upper()).pack(anchor="w", pady=(0, 4))
            w(box).pack(fill="x")

        def mk_out(p):
            r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x")
            self.out_var = tk.StringVar(value=config.load_settings()["output_dir"])
            T.entry(r, self.out_var, width=10).pack(side="left", fill="x", expand=True)
            T.ghost_button(r, "Browse", self._pick_out, width=90).pack(side="left", padx=(8, 0))
        T.field(left_in, 7, "Output directory", mk_out)

        # right column
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        prev = T.card(right)
        prev.pack(fill="x")
        T.heading(prev, "PREVIEW").pack(anchor="w", padx=18, pady=(14, 6))
        self.thumb_lbl = T.label(prev, "Select a video to see its first frame", 12, "normal", T.MUTED, height=190)
        self.thumb_lbl.pack(fill="x", padx=18)
        self.btn_preview = T.ghost_button(prev, "▶  Render 3-second preview", self._preview)
        self.btn_preview.pack(fill="x", padx=18, pady=14)

        prog = T.card(right)
        prog.pack(fill="x", pady=(14, 0))
        pin = ctk.CTkFrame(prog, fg_color="transparent"); pin.pack(fill="x", padx=18, pady=16)
        T.heading(pin, "PROCESSING").pack(anchor="w", pady=(0, 8))
        self.progress = T.ProgressPanel(pin)
        self.progress.pack(fill="x")
        btns = ctk.CTkFrame(pin, fg_color="transparent"); btns.pack(fill="x", pady=(14, 0))
        btns.columnconfigure(0, weight=1)
        self.btn_start = T.primary_button(btns, "Start Interpolation", self._start)
        self.btn_start.grid(row=0, column=0, sticky="ew")
        self.btn_cancel = T.danger_button(btns, "Cancel", self._cancel, width=100, state="disabled")
        self.btn_cancel.grid(row=0, column=1, padx=(8, 0))

        self.note = T.label(right, "", 12, "normal", T.MUTED, anchor="w", justify="left", wraplength=380)
        self.note.pack(fill="x", pady=(10, 0))

    # ------------------------------------------------------------------------------------------ input
    def _pick_input(self):
        p = T.browse_file()
        if p:
            self.load_video(p)

    def _pick_out(self):
        p = T.browse_folder()
        if p:
            self.out_var.set(p)

    def load_video(self, path: str):
        try:
            info = analyze(path)
        except StudioError as e:
            messagebox.showerror("Cannot open video", str(e))
            return
        self.info = info
        self.in_var.set(path)
        self.grid_info.set(info.summary_lines())
        self.orig_var.set(fmt_fps(info.fps_float))
        self._set_mult("2x")
        notes = []
        if info.is_vfr:
            notes.append("Variable frame rate detected — it will be converted to constant frame rate before interpolation.")
        self.note.configure(text="\n".join(notes))
        try:
            tmp = os.path.join(tempfile.gettempdir(), "ff_thumb.png")
            if extract_thumbnail(path, tmp, min(1.0, info.duration / 2), 640):
                from PIL import Image
                im = Image.open(tmp); im.load()
                h = 190; w = int(im.width * h / im.height)
                self._thumb = ctk.CTkImage(light_image=im, dark_image=im, size=(w, h))
                self.thumb_lbl.configure(image=self._thumb, text="")
        except Exception:
            self.thumb_lbl.configure(text="Preview unavailable", image=None)

    # ------------------------------------------------------------------------------------------ fps linking
    def _set_mult(self, m: str):
        self.mult_var.set(m)
        self._on_mult(m)

    def _on_mult(self, m: str):
        if not self.info or self._sync_lock:
            return
        self._exact_target = self.info.fps * int(m[:-1])
        self._sync_lock = True
        self.target_var.set(fmt_fps(float(self._exact_target)))
        self._sync_lock = False

    def _on_target_typed(self, *_):
        if self._sync_lock or not self.info:
            return
        try:
            t = float(self.target_var.get())
        except ValueError:
            return
        self._exact_target = None
        ratio = t / self.info.fps_float
        if ratio > 1:
            import math
            self._sync_lock = True
            m = math.ceil(ratio - 1e-6)
            self.mult_var.set(f"{m}x" if f"{m}x" in MULTS else self.mult_var.get())
            self._sync_lock = False

    def _target(self) -> Fraction:
        txt = self.target_var.get().strip().replace(",", ".")
        try:
            val = Fraction(txt)
        except (ValueError, ZeroDivisionError):
            raise StudioError("Target FPS is not a valid number.")
        if self._exact_target is not None and abs(float(self._exact_target) - float(val)) < 0.0006:
            return self._exact_target
        return val

    # ------------------------------------------------------------------------------------------ run
    def _make_job(self, preview: bool) -> "rife_engine.InterpolationJob":
        if not self.info:
            raise StudioError("Choose an input video first.")
        if not self._models:
            raise StudioError("No RIFE model found. Install rife-ncnn-vulkan (see Settings → Engine status).")
        target = self._target()
        try:
            batch = int(self.batch_var.get())
        except ValueError:
            raise StudioError("Batch size must be a whole number.")
        preset = {"Fast": "fast", "Balanced": "balanced", "High Quality": "high"}[self.preset_var.get()]
        ext = FORMATS[self.fmt_var.get()][0]
        stem = os.path.splitext(os.path.basename(self.info.path))[0]
        if preview:
            out = os.path.join(tempfile.gettempdir(), f"ff_preview_{os.getpid()}.{ext}")
            if os.path.exists(out):
                os.remove(out)
        else:
            out = unique_path(self.out_var.get(), stem, f"{fmt_fps(float(target))}fps_RIFE", "." + ext)
        return rife_engine.InterpolationJob(
            self.info.path, out, target, self._models[self.model_var.get()].name, self._dev[self.dev_var.get()], preset,
            self.fmt_var.get(), RESOLUTIONS[self.res_var.get()], batch, 3.0 if preview else None)

    def _preview(self):
        self._run(True)

    def _start(self):
        self._run(False)

    def _run(self, preview: bool):
        if self.task and self.task.running:
            return
        try:
            job = self._make_job(preview)
        except StudioError as e:
            messagebox.showwarning("Check your settings", str(e))
            return
        mode = "AI Frame Interpolation (RIFE)"

        def work(progress, cancel):
            res = rife_engine.run(job, progress, cancel)
            summary = summarize_output(job.output_path, mode, res.elapsed,
                                       {"Interpolation": f"{res.multiplier}× · {job.model}",
                                        "Validation": "passed" if res.report.passed else "FAILED"})
            summary["report"] = res.report.text()
            return summary

        self.task = BackgroundTask(work)
        self.task.start()
        self._set_busy(True)
        self.progress.start()
        self._preview_mode = preview
        self.after(120, self._poll)

    def _poll(self):
        if not self.task:
            return
        for m in self.task.poll():
            kind = m[0]
            if kind == "progress":
                _, frac, text, extra = m
                self.progress.set(frac, text, extra.get("eta"), extra.get("fps"))
            elif kind == "done":
                self._set_busy(False)
                self.progress.finish("Finished")
                summary = m[1]
                if self._preview_mode:
                    open_file(summary["path"])
                    self.progress.finish("Preview ready — opened in your video player")
                else:
                    record_history(summary, self.info.path)
                    self.app.show_completion(summary)
                return
            elif kind == "cancelled":
                self._set_busy(False)
                self.progress.finish("Cancelled", ok=False)
                return
            elif kind == "error":
                self._set_busy(False)
                self.progress.finish("Failed", ok=False)
                messagebox.showerror("Interpolation failed", str(m[1]))
                return
        self.after(120, self._poll)

    def _cancel(self):
        if self.task:
            self.task.cancel()
            self.progress.set(0, "Cancelling…")

    def _set_busy(self, busy: bool):
        for b in (self.btn_start, self.btn_preview):
            b.configure(state="disabled" if busy else "normal")
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def on_show(self):
        pass


def _ro(parent, var):
    e = T.entry(parent, var, width=10)
    e.configure(state="readonly")
    return e


def _tgt(parent, var, cb):
    var.trace_add("write", cb)
    return T.entry(parent, var, "e.g. 60", width=10)


def _pack(w):
    w.pack(fill="x")
    return w
