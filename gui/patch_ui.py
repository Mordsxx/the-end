"""Workspace 2 - TikTok 60FPS Patch (native MP4 timing patcher). Independent from the interpolation workspace."""
import os
import tkinter as tk
from fractions import Fraction
from tkinter import messagebox

import customtkinter as ctk

from core import config
from core.errors import StudioError
from core.process_manager import BackgroundTask
from core.video_analyzer import analyze
from engines.mp4_patch import mp4_patcher
from engines.mp4_patch.timing_engine import SlowFactor
from . import theme as T
from .common import fmt_fps, record_history, summarize_output, unique_path


class PatchPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.summary = None          # mp4_patcher.Mp4Summary
        self.path = ""
        self.task: BackgroundTask | None = None
        self._lock = False
        self._last_edit = "mult"
        self._build()

    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        T.label(head, "TikTok 60FPS Patch", 24, "bold").pack(anchor="w")
        T.label(head, "Change playback timing at the MP4 container level — every encoded video frame stays untouched.",
                13, "normal", T.MUTED).pack(anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="c")
        body.columnconfigure(1, weight=4, uniform="c")

        left = T.card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        li = ctk.CTkFrame(left, fg_color="transparent"); li.pack(fill="both", expand=True, padx=18, pady=16)
        li.columnconfigure(0, weight=1)

        def mk_input(p):
            r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x")
            self.in_var = tk.StringVar()
            e = T.entry(r, self.in_var, "Choose an MP4 video…", width=10); e.pack(side="left", fill="x", expand=True)
            e.configure(state="readonly")
            T.ghost_button(r, "Browse", self._pick_input, width=90).pack(side="left", padx=(8, 0))
        T.field(li, 0, "Input video", mk_input)

        self.grid_info = T.InfoGrid(li)
        self.grid_info.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.grid_info.clear()

        row = ctk.CTkFrame(li, fg_color="transparent"); row.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        row.columnconfigure(0, weight=1, uniform="p"); row.columnconfigure(1, weight=1, uniform="p")
        self.target_var, self.mult_var = tk.StringVar(), tk.StringVar(value="2")
        for i, (cap, var, cb) in enumerate([("Target FPS", self.target_var, self._on_target),
                                            ("Playback speed multiplier (slower ×)", self.mult_var, self._on_mult)]):
            box = ctk.CTkFrame(row, fg_color="transparent")
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            T.heading(box, cap.upper()).pack(anchor="w", pady=(0, 4))
            var.trace_add("write", cb)
            T.entry(box, var, width=10).pack(fill="x")

        quick = ctk.CTkFrame(li, fg_color="transparent"); quick.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        for txt, m in [("2× slower  (60→30)", "2"), ("3× slower", "3"), ("4× slower  (60→15)", "4")]:
            T.ghost_button(quick, txt, lambda m=m: self._quick(m), height=30).pack(side="left", padx=(0, 8))

        self.audio_var = tk.StringVar(value="Keep original audio")
        T.field(li, 4, "Audio", lambda p: _pk(T.segmented(p, ["Keep original audio", "Slow audio too", "Remove audio"], self.audio_var)))

        def mk_out(p):
            r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x")
            self.out_var = tk.StringVar(value=config.load_settings()["output_dir"])
            T.entry(r, self.out_var, width=10).pack(side="left", fill="x", expand=True)
            T.ghost_button(r, "Browse", self._pick_out, width=90).pack(side="left", padx=(8, 0))
        T.field(li, 5, "Output directory (the source file is never modified)", mk_out)

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        prog = T.card(right); prog.pack(fill="x")
        pin = ctk.CTkFrame(prog, fg_color="transparent"); pin.pack(fill="x", padx=18, pady=16)
        T.heading(pin, "PROCESSING").pack(anchor="w", pady=(0, 8))
        self.progress = T.ProgressPanel(pin); self.progress.pack(fill="x")
        btns = ctk.CTkFrame(pin, fg_color="transparent"); btns.pack(fill="x", pady=(14, 0))
        btns.columnconfigure(0, weight=1)
        self.btn_start = T.primary_button(btns, "Apply Timing Patch", self._start)
        self.btn_start.grid(row=0, column=0, sticky="ew")
        self.btn_cancel = T.danger_button(btns, "Cancel", self._cancel, width=100, state="disabled")
        self.btn_cancel.grid(row=0, column=1, padx=(8, 0))

        res = T.card(right); res.pack(fill="both", expand=True, pady=(14, 0))
        T.heading(res, "VALIDATION RESULTS").pack(anchor="w", padx=18, pady=(14, 6))
        self.log = T.textbox(res, height=260)
        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self._log("Select an MP4 to inspect its timing structure.")

    # -------------------------------------------------------------------------------------- helpers
    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", text)
        self.log.configure(state="disabled")

    def _pick_input(self):
        p = T.browse_file("Select an MP4 video")
        if p:
            self.load_video(p)

    def _pick_out(self):
        p = T.browse_folder()
        if p:
            self.out_var.set(p)

    def load_video(self, path: str):
        try:
            s = mp4_patcher.inspect(path)
        except StudioError as e:
            messagebox.showerror("Cannot use this file", str(e))
            return
        self.summary, self.path = s, path
        self.in_var.set(path)
        rows = [("Container brand", s.brand),
                ("Original FPS", f"{s.fps_float:.3f}" + ("  · VARIABLE frame rate" if s.is_vfr else "  · constant")),
                ("Original duration", f"{float(s.duration):.3f} s"),
                ("Original frame count", str(s.frame_count)),
                ("Video timescale", str(s.video_timescale)),
                ("Audio", f"{s.audio_rate} Hz · {float(s.audio_duration):.3f} s" if s.has_audio else "none")]
        try:
            v = analyze(path)
            rows[1:1] = [("Resolution", v.resolution), ("Video codec", f"{v.video_codec} · {v.pix_fmt}"),
                         ("Audio codec", v.audio_codec or "none")]
        except StudioError:
            pass
        self.grid_info.set(rows)
        self._quick("2")
        msg = ["File accepted. Tracks: %d." % s.tracks]
        if s.is_vfr:
            msg.append("Variable frame rate: every sample's timing will be scaled uniformly.")
        self._log("\n".join(msg))

    def _quick(self, m: str):
        self._last_edit = "mult"
        self.mult_var.set(m)

    def _on_mult(self, *_):
        if self._lock or not self.summary:
            return
        self._last_edit = "mult"
        try:
            m = Fraction(self.mult_var.get().replace(",", "."))
            if m <= 0:
                return
        except (ValueError, ZeroDivisionError):
            return
        self._lock = True
        self.target_var.set(fmt_fps(float(self.summary.fps / m)))
        self._lock = False

    def _on_target(self, *_):
        if self._lock or not self.summary:
            return
        self._last_edit = "target"
        try:
            t = Fraction(self.target_var.get().replace(",", "."))
            if t <= 0:
                return
        except (ValueError, ZeroDivisionError):
            return
        self._lock = True
        self.mult_var.set(fmt_fps(float(self.summary.fps / t)))
        self._lock = False

    def _factor(self) -> SlowFactor:
        if self._last_edit == "target":
            return SlowFactor.from_fps(self.summary.fps, self.target_var.get().replace(",", "."))
        return SlowFactor.from_multiplier(self.mult_var.get().replace(",", "."))

    # -------------------------------------------------------------------------------------- run
    def _start(self):
        if self.task and self.task.running:
            return
        if not self.summary:
            messagebox.showwarning("Check your settings", "Choose an MP4 video first.")
            return
        try:
            factor = self._factor()
        except Exception as e:
            messagebox.showwarning("Check your settings", f"Invalid speed/FPS value: {e}")
            return
        if factor.ratio == 1:
            messagebox.showwarning("Check your settings", "Speed multiplier 1× would change nothing.")
            return
        out_fps = factor.target_fps(self.summary.fps)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        out = unique_path(self.out_var.get(), stem, f"{fmt_fps(float(out_fps))}fps_patched", ".mp4")
        audio_mode = {"Keep original audio": "keep", "Slow audio too": "reencode", "Remove audio": "drop"}[self.audio_var.get()]
        src = self.path
        mode = "TikTok 60FPS Patch (native MP4 timing)"

        def work(progress, cancel):
            res = mp4_patcher.patch(src, out, factor, progress, cancel, audio_mode=audio_mode)
            summary = summarize_output(out, mode, res.elapsed,
                                       {"Speed": f"{float(factor.ratio):g}× slower",
                                        "Frame count preserved": f"{res.frame_count} frames",
                                        "Validation": "passed" if res.report.passed else "FAILED"})
            summary["report"] = res.report.text() + "\n\nPatch details:\n  " + "\n  ".join(res.notes)
            return summary

        self.task = BackgroundTask(work)
        self.task.start()
        self._busy(True)
        self.progress.start()
        self._log("Working…")
        self.after(120, self._poll)

    def _poll(self):
        for m in self.task.poll():
            k = m[0]
            if k == "progress":
                self.progress.set(m[1], m[2])
            elif k == "done":
                self._busy(False)
                self.progress.finish("Finished")
                self._log(m[1]["report"])
                record_history(m[1], self.path)
                self.app.show_completion(m[1])
                return
            elif k == "cancelled":
                self._busy(False)
                self.progress.finish("Cancelled", ok=False)
                self._log("Cancelled. No output file was written.")
                return
            elif k == "error":
                self._busy(False)
                self.progress.finish("Failed", ok=False)
                self._log(str(m[1]))
                messagebox.showerror("Patch failed", str(m[1])[:900])
                return
        self.after(120, self._poll)

    def _cancel(self):
        if self.task:
            self.task.cancel()

    def _busy(self, b: bool):
        self.btn_start.configure(state="disabled" if b else "normal")
        self.btn_cancel.configure(state="normal" if b else "disabled")

    def on_show(self):
        pass


def _pk(w):
    w.pack(fill="x")
    return w
