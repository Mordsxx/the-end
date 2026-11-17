import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import config
from core.ffmpeg_manager import ffmpeg_path, ffmpeg_version, ffprobe_path
from engines.interpolation import model_manager
from . import theme as T


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        T.label(self, "Settings", 24, "bold").pack(anchor="w", pady=(0, 16))
        c = T.card(self); c.pack(fill="x")
        inner = ctk.CTkFrame(c, fg_color="transparent"); inner.pack(fill="x", padx=22, pady=18)
        inner.columnconfigure(0, weight=1)
        s = config.load_settings()
        self.vars = {k: tk.StringVar(value=s.get(k, "")) for k in ("output_dir", "ffmpeg_path", "ffprobe_path", "rife_dir")}
        rows = [("Default output folder", "output_dir", True), ("FFmpeg executable (optional override)", "ffmpeg_path", False),
                ("FFprobe executable (optional override)", "ffprobe_path", False),
                ("RIFE folder (contains rife-ncnn-vulkan, optional override)", "rife_dir", True)]
        for i, (cap, key, folder) in enumerate(rows):
            def mk(p, key=key, folder=folder):
                r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x")
                T.entry(r, self.vars[key], width=10).pack(side="left", fill="x", expand=True)
                T.ghost_button(r, "Browse", lambda: self._browse(key, folder), width=90).pack(side="left", padx=(8, 0))
            T.field(inner, i, cap, mk)
        b = ctk.CTkFrame(inner, fg_color="transparent"); b.grid(row=len(rows), column=0, sticky="w", pady=(4, 0))
        T.primary_button(b, "Save settings", self._save, width=160).pack(side="left")
        T.ghost_button(b, "Clear history", self._clear, width=140).pack(side="left", padx=8)

        self.status = T.card(self); self.status.pack(fill="x", pady=14)

    def _browse(self, key, folder):
        p = T.browse_folder() if folder else T.filedialog.askopenfilename()
        if p:
            self.vars[key].set(p)

    def _save(self):
        s = config.load_settings()
        s.update({k: v.get().strip() for k, v in self.vars.items()})
        config.save_settings(s)
        self.on_show()
        messagebox.showinfo("Settings", "Settings saved.")

    def _clear(self):
        config.clear_history()

    def on_show(self):
        for w in self.status.winfo_children():
            w.destroy()
        T.heading(self.status, "ENGINE STATUS").pack(anchor="w", padx=22, pady=(16, 8))
        models = model_manager.list_models()
        rife = model_manager.find_rife_dir()
        g = T.InfoGrid(self.status); g.pack(fill="x", padx=22, pady=(0, 18))
        g.set([("FFmpeg", ffmpeg_version()[:60] if ffmpeg_path(required=False) else "not found"),
               ("FFprobe", "found" if ffprobe_path(required=False) else "not found"),
               ("rife-ncnn-vulkan", str(rife) if rife else "not found — see docs/MODELS.md"),
               ("RIFE models", ", ".join(m.name for m in models) or "none")])
