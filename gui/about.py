import webbrowser

import customtkinter as ctk
from PIL import Image

from core.paths import resource_path
from . import branding as B
from . import theme as T


class AboutPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        T.label(self, "About", 24, "bold").pack(anchor="w", pady=(0, 16))
        c = T.card(self, corner_radius=18); c.pack(fill="x")
        inner = ctk.CTkFrame(c, fg_color="transparent"); inner.pack(fill="x", padx=30, pady=28)
        try:
            im = Image.open(resource_path("assets", "icon.png"))
            ctk.CTkLabel(inner, text="", image=ctk.CTkImage(light_image=im, dark_image=im, size=(120, 120))).pack(side="left", padx=(0, 28))
        except Exception:
            pass
        col = ctk.CTkFrame(inner, fg_color="transparent"); col.pack(side="left", fill="x", expand=True)
        T.label(col, B.APP_NAME, 26, "bold", anchor="w").pack(anchor="w")
        T.label(col, f"Version {B.VERSION}", 13, "normal", T.MUTED, anchor="w").pack(anchor="w", pady=(2, 12))
        T.label(col, B.DESCRIPTION, 13, "normal", "#CFCFCF", anchor="w", justify="left", wraplength=560).pack(anchor="w")

        dev = T.card(self); dev.pack(fill="x", pady=14)
        di = ctk.CTkFrame(dev, fg_color="transparent"); di.pack(fill="x", padx=30, pady=22)
        T.heading(di, "DEVELOPER").pack(anchor="w")
        T.label(di, B.AUTHOR, 20, "bold", anchor="w").pack(anchor="w", pady=(6, 0))
        T.label(di, B.TIKTOK, 15, "bold", T.ACCENT_H, anchor="w").pack(anchor="w", pady=(2, 12))
        T.ghost_button(di, "Open TikTok profile", lambda: webbrowser.open(B.TIKTOK_URL), width=170).pack(anchor="w")

        tech = T.card(self); tech.pack(fill="x")
        ti = ctk.CTkFrame(tech, fg_color="transparent"); ti.pack(fill="x", padx=30, pady=20)
        T.heading(ti, "TECHNOLOGY").pack(anchor="w", pady=(0, 6))
        for line in ("AI interpolation: RIFE via rife-ncnn-vulkan (Vulkan GPU, NVIDIA / AMD / Intel)",
                     "MP4 patching: native ISO-BMFF parser — no frame is decoded or re-encoded",
                     "Media tools: FFmpeg / FFprobe"):
            T.label(ti, "•  " + line, 12, "normal", T.MUTED, anchor="w").pack(anchor="w")

    def on_show(self):
        pass
