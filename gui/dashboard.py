import customtkinter as ctk

from core import config, hardware_detector
from core.ffmpeg_manager import ffmpeg_path
from engines.interpolation import model_manager
from . import icons
from . import theme as T


class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        T.label(self, "Dashboard", 24, "bold").pack(anchor="w")
        T.label(self, "Two independent engines. Choose the workflow you need.", 13, "normal", T.MUTED).pack(anchor="w", pady=(0, 16))

        cards = ctk.CTkFrame(self, fg_color="transparent"); cards.pack(fill="x")
        cards.columnconfigure(0, weight=1, uniform="k"); cards.columnconfigure(1, weight=1, uniform="k")
        self._feature(cards, 0, icons.interpolation(256, 84), "AI Frame Interpolation",
                      "Generate brand-new in-between frames with RIFE. Turn 30 FPS into 60 or 120 for smooth, natural motion — "
                      "built for gaming, anime and fast action.", "interpolation")
        self._feature(cards, 1, icons.patch(256, 84), "TikTok 60FPS Patch",
                      "Rewrite MP4 timing metadata to change playback speed — e.g. 60 FPS → 30 FPS — while every encoded "
                      "video frame stays untouched. Fast and lossless.", "patch")

        lower = ctk.CTkFrame(self, fg_color="transparent"); lower.pack(fill="both", expand=True, pady=(14, 0))
        lower.columnconfigure(0, weight=1, uniform="l"); lower.columnconfigure(1, weight=1, uniform="l")
        self.hw = T.card(lower); self.hw.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.hist = T.card(lower); self.hist.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

    def _feature(self, parent, col, image, title, text, page):
        c = T.card(parent, corner_radius=18)
        c.grid(row=0, column=col, sticky="nsew", padx=(0, 8) if col == 0 else (8, 0))
        T.hover_card(c)
        inner = ctk.CTkFrame(c, fg_color="transparent"); inner.pack(fill="both", expand=True, padx=24, pady=22)
        ctk.CTkLabel(inner, text="", image=image).pack(anchor="w")
        T.label(inner, title, 20, "bold", anchor="w").pack(anchor="w", pady=(10, 4))
        T.label(inner, text, 13, "normal", T.MUTED, anchor="w", justify="left", wraplength=380).pack(anchor="w", fill="x")
        T.primary_button(inner, "Open Workspace  →", lambda: self.app.show_page(page), width=190).pack(anchor="w", pady=(16, 0))

    def on_show(self):
        for w in self.hw.winfo_children() + self.hist.winfo_children():
            w.destroy()
        # hardware
        T.heading(self.hw, "HARDWARE STATUS").pack(anchor="w", padx=18, pady=(14, 8))
        hw = hardware_detector.detect()
        rows = [("CPU", f"{hw.cpu} · {hw.cores} threads"), ("Memory", f"{hw.ram_gb} GB" if hw.ram_gb else "unknown"),
                ("GPU", "; ".join(g.label for g in hw.gpus) or "No GPU detected (CPU fallback)"),
                ("FFmpeg", "ready" if ffmpeg_path(required=False) else "NOT FOUND"),
                ("RIFE engine", f"{len(model_manager.list_models())} model(s) found" if model_manager.find_rife_dir() else "NOT FOUND — see Settings")]
        g = T.InfoGrid(self.hw); g.pack(fill="x", padx=18, pady=(0, 16)); g.set(rows)
        # history
        T.heading(self.hist, "RECENT PROCESSING").pack(anchor="w", padx=18, pady=(14, 8))
        hist = config.load_history()[:5]
        if not hist:
            T.label(self.hist, "Nothing processed yet.", 13, "normal", T.MUTED).pack(anchor="w", padx=18, pady=(0, 16))
        for h in hist:
            row = ctk.CTkFrame(self.hist, fg_color=T.BG2, corner_radius=10, border_width=1, border_color=T.BORDER)
            row.pack(fill="x", padx=18, pady=(0, 6))
            T.label(row, h.get("input", ""), 13, "bold", anchor="w").pack(anchor="w", padx=12, pady=(7, 0))
            T.label(row, f"{h.get('mode', '')} · {h.get('fps', '')} FPS · {h.get('when', '')}", 11, "normal", T.MUTED,
                    anchor="w").pack(anchor="w", padx=12, pady=(0, 7))
        ctk.CTkFrame(self.hist, fg_color="transparent", height=10).pack()
