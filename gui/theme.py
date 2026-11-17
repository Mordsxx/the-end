"""Pure Black Matte design system + small reusable widgets."""
import itertools
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

BG = "#080808"
BG2 = "#101010"
CARD = "#151515"
ELEV = "#1B1B1B"
BORDER = "#292929"
TEXT = "#FFFFFF"
MUTED = "#999999"
ACCENT = "#8B5CF6"
ACCENT_H = "#A78BFA"
DANGER = "#EF4444"
DANGER_H = "#F87171"
OK = "#22C55E"
WARN = "#F59E0B"

FAMILY = "Segoe UI"
_fonts: dict = {}


def font(size: int = 13, weight: str = "normal") -> "ctk.CTkFont":
    """Fonts must be created after the root window exists, so they are built lazily."""
    key = (size, weight)
    if key not in _fonts:
        _fonts[key] = ctk.CTkFont(family=FAMILY, size=size, weight=weight)
    return _fonts[key]


def init() -> None:
    ctk.set_appearance_mode("dark")


# ---------------------------------------------------------------------------------------- basic widgets

def card(master, **kw) -> ctk.CTkFrame:
    kw.setdefault("fg_color", CARD)
    kw.setdefault("border_color", BORDER)
    kw.setdefault("border_width", 1)
    kw.setdefault("corner_radius", 14)
    return ctk.CTkFrame(master, **kw)


def label(master, text="", size=13, weight="normal", color=TEXT, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, font=font(size, weight), text_color=color, **kw)


def heading(master, text, **kw):
    return label(master, text, 12, "bold", MUTED, anchor="w", **kw)


def primary_button(master, text, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 40)
    return ctk.CTkButton(master, text=text, command=command, fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT,
                         corner_radius=10, font=font(13, "bold"), **kw)


def ghost_button(master, text, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, fg_color=ELEV, hover_color="#242424", text_color=TEXT,
                         border_width=1, border_color=BORDER, corner_radius=10, font=font(13), **kw)


def danger_button(master, text, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 40)
    return ctk.CTkButton(master, text=text, command=command, fg_color="#2A1212", hover_color="#3A1717", text_color=DANGER_H,
                         border_width=1, border_color="#4A1D1D", corner_radius=10, font=font(13, "bold"), **kw)


def entry(master, variable=None, placeholder="", width=140, **kw) -> ctk.CTkEntry:
    return ctk.CTkEntry(master, textvariable=variable, placeholder_text=placeholder, width=width, height=36,
                        fg_color=BG2, border_color=BORDER, border_width=1, text_color=TEXT,
                        placeholder_text_color="#555555", corner_radius=9, font=font(13), **kw)


def option_menu(master, values, variable=None, command=None, width=200, **kw) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(master, values=list(values) or [""], variable=variable, command=command, width=width,
                             height=36, fg_color=BG2, button_color=ELEV, button_hover_color="#2A2A2A",
                             dropdown_fg_color=ELEV, dropdown_hover_color="#2A2A2A", dropdown_text_color=TEXT,
                             text_color=TEXT, corner_radius=9, font=font(13), dropdown_font=font(13), **kw)


def segmented(master, values, variable=None, command=None, **kw) -> ctk.CTkSegmentedButton:
    return ctk.CTkSegmentedButton(master, values=list(values), variable=variable, command=command,
                                  fg_color=BG2, selected_color=ACCENT, selected_hover_color=ACCENT_H,
                                  unselected_color=BG2, unselected_hover_color=ELEV, text_color=TEXT,
                                  corner_radius=9, font=font(12, "bold"), **kw)


def textbox(master, **kw) -> ctk.CTkTextbox:
    return ctk.CTkTextbox(master, fg_color=BG2, text_color=TEXT, border_width=1, border_color=BORDER,
                          corner_radius=10, font=ctk.CTkFont(family="Consolas", size=12), **kw)


def field(parent, row: int, caption: str, widget_factory, col_span: int = 1):
    """Caption above a widget inside a grid parent."""
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    wrap.grid(row=row, column=0, columnspan=col_span, sticky="ew", pady=(0, 12))
    heading(wrap, caption.upper()).pack(anchor="w", pady=(0, 4))
    w = widget_factory(wrap)
    return wrap, w


def browse_file(title="Select video") -> str:
    return filedialog.askopenfilename(
        title=title, filetypes=[("Video files", "*.mp4 *.mov *.m4v *.mkv *.avi *.webm *.ts *.flv"), ("All files", "*.*")])


def browse_folder(title="Select output folder") -> str:
    return filedialog.askdirectory(title=title)


# ---------------------------------------------------------------------------------------- composite widgets

class InfoGrid(ctk.CTkFrame):
    """Two-column key/value list used for video information."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=BG2, corner_radius=10, border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(1, weight=1)
        self._rows: list = []

    def set(self, items: list) -> None:
        for a, b in self._rows:
            a.destroy(); b.destroy()
        self._rows.clear()
        for i, (k, v) in enumerate(items):
            a = label(self, k, 12, "normal", MUTED, anchor="w")
            b = label(self, str(v), 12, "bold", TEXT, anchor="e", justify="right", wraplength=300)
            a.grid(row=i, column=0, sticky="w", padx=(14, 8), pady=3)
            b.grid(row=i, column=1, sticky="e", padx=(8, 14), pady=3)
            self._rows.append((a, b))

    def clear(self, text="No video selected"):
        self.set([("Status", text)])


class ProgressPanel(ctk.CTkFrame):
    """Elegant progress bar with eased animation, spinner, percentage and ETA."""
    SPIN = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")

    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        self.spin = label(top, "", 16, "bold", ACCENT, width=22)
        self.spin.pack(side="left")
        self.status = label(top, "Idle", 13, "bold", TEXT, anchor="w")
        self.status.pack(side="left", padx=(6, 0))
        self.pct = label(top, "0%", 13, "bold", ACCENT_H)
        self.pct.pack(side="right")
        self.bar = ctk.CTkProgressBar(self, height=10, corner_radius=6, fg_color=ELEV, progress_color=ACCENT)
        self.bar.pack(fill="x", pady=(8, 6))
        self.bar.set(0)
        self.detail = label(self, "", 12, "normal", MUTED, anchor="w")
        self.detail.pack(fill="x")
        self._target = 0.0
        self._shown = 0.0
        self._spinning = False

    # -- public --
    def start(self):
        self._spinning = True
        self.set(0.0, "Starting…")
        self._tick()

    def set(self, frac: float, text: str = "", eta: float | None = None, fps: float | None = None):
        self._target = max(0.0, min(1.0, frac))
        if text:
            self.status.configure(text=text)
        bits = []
        if fps:
            bits.append(f"{fps:.1f} source frames/s")
        if eta is not None:
            bits.append(f"≈ {_fmt_time(eta)} remaining")
        self.detail.configure(text="   ·   ".join(bits))
        self._animate()

    def finish(self, text="Done", ok=True):
        self._spinning = False
        self.spin.configure(text="✔" if ok else "✖", text_color=OK if ok else DANGER)
        self.status.configure(text=text)
        self._target = 1.0 if ok else self._target
        self.detail.configure(text="")
        self._animate()

    def reset(self):
        self._spinning = False
        self._target = self._shown = 0.0
        self.bar.set(0)
        self.pct.configure(text="0%")
        self.spin.configure(text="", text_color=ACCENT)
        self.status.configure(text="Idle")
        self.detail.configure(text="")

    # -- internals --
    def _animate(self):
        diff = self._target - self._shown
        if abs(diff) < 0.002:
            self._shown = self._target
        else:
            self._shown += diff * 0.35
            self.after(30, self._animate)
        self.bar.set(self._shown)
        self.pct.configure(text=f"{int(self._shown * 100)}%")

    def _tick(self):
        if self._spinning:
            self.spin.configure(text=next(self.SPIN), text_color=ACCENT)
            self.after(90, self._tick)


def _fmt_time(sec: float) -> str:
    sec = int(max(0, sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m" if h else (f"{m}m {s:02d}s" if m else f"{s}s")


def fmt_time(sec: float) -> str:
    return _fmt_time(sec)


def hover_card(frame: ctk.CTkFrame) -> None:
    """Subtle accent border on hover for clickable cards."""
    def on(_e): frame.configure(border_color=ACCENT)
    def off(_e): frame.configure(border_color=BORDER)
    frame.bind("<Enter>", on)
    frame.bind("<Leave>", off)
