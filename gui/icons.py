"""Procedurally drawn, anti-aliased icons (no icon fonts or external assets needed)."""
from PIL import Image, ImageDraw
import customtkinter as ctk

ACCENT = (139, 92, 246, 255)
ACCENT_SOFT = (139, 92, 246, 70)
WHITE = (255, 255, 255, 255)
GREY = (153, 153, 153, 255)
SS = 4  # supersampling


def _canvas(size):
    return Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))


def _finish(img, size, px):
    img = img.resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(px, px))


def interpolation(size=128, px=None, color=ACCENT):
    im = _canvas(size); d = ImageDraw.Draw(im); s = size * SS
    w, h = s * 0.20, s * 0.50
    y0 = s * 0.25
    lw = max(2, int(s * 0.03))
    xs = [s * 0.10, s * 0.40, s * 0.70]
    for i, x in enumerate(xs):
        box = (x, y0, x + w, y0 + h)
        if i == 1:   # the AI-generated in-between frame
            d.rounded_rectangle(box, radius=s * 0.04, fill=ACCENT_SOFT, outline=color, width=lw)
            cx, cy = x + w / 2, y0 + h / 2
            r = s * 0.045
            d.polygon([(cx, cy - 2 * r), (cx + r * .6, cy - r * .6), (cx + 2 * r, cy), (cx + r * .6, cy + r * .6),
                       (cx, cy + 2 * r), (cx - r * .6, cy + r * .6), (cx - 2 * r, cy), (cx - r * .6, cy - r * .6)], fill=WHITE)
        else:
            d.rounded_rectangle(box, radius=s * 0.04, outline=color, width=lw)
            d.line([(x + w * 0.25, y0 + h * 0.3), (x + w * 0.75, y0 + h * 0.3)], fill=GREY, width=lw)
    return _finish(im, size, px or size)


def patch(size=128, px=None, color=ACCENT):
    im = _canvas(size); d = ImageDraw.Draw(im); s = size * SS
    lw = max(2, int(s * 0.035))
    d.ellipse((s * 0.14, s * 0.14, s * 0.86, s * 0.86), outline=color, width=lw)
    c = s / 2
    d.line([(c, c), (c, s * 0.28)], fill=WHITE, width=lw)
    d.line([(c, c), (s * 0.66, s * 0.60)], fill=WHITE, width=lw)
    d.ellipse((c - lw, c - lw, c + lw, c + lw), fill=WHITE)
    for dx in (0, s * 0.10):   # slow-down chevrons
        d.line([(s * 0.62 + dx, s * 0.10), (s * 0.72 + dx, s * 0.18), (s * 0.62 + dx, s * 0.26)], fill=color, width=lw)
    return _finish(im, size, px or size)


def nav(name: str, px=20, color=GREY):
    size = 64
    im = _canvas(size); d = ImageDraw.Draw(im); s = size * SS
    lw = max(2, int(s * 0.07))
    if name == "dashboard":
        for x in (0.14, 0.54):
            for y in (0.14, 0.54):
                d.rounded_rectangle((s * x, s * y, s * (x + 0.32), s * (y + 0.32)), radius=s * 0.06, outline=color, width=lw)
    elif name == "interpolation":
        for x in (0.12, 0.40, 0.68):
            d.rounded_rectangle((s * x, s * 0.25, s * (x + 0.20), s * 0.75), radius=s * 0.05, outline=color, width=lw)
    elif name == "patch":
        d.ellipse((s * 0.12, s * 0.12, s * 0.88, s * 0.88), outline=color, width=lw)
        d.line([(s / 2, s / 2), (s / 2, s * 0.28)], fill=color, width=lw)
        d.line([(s / 2, s / 2), (s * 0.66, s * 0.6)], fill=color, width=lw)
    elif name == "about":
        d.ellipse((s * 0.12, s * 0.12, s * 0.88, s * 0.88), outline=color, width=lw)
        d.line([(s / 2, s * 0.44), (s / 2, s * 0.70)], fill=color, width=lw)
        d.ellipse((s * 0.46, s * 0.27, s * 0.54, s * 0.35), fill=color)
    elif name == "settings":
        for y in (0.28, 0.5, 0.72):
            d.line([(s * 0.14, s * y), (s * 0.86, s * y)], fill=color, width=lw)
        for x, y in ((0.35, 0.28), (0.65, 0.5), (0.45, 0.72)):
            d.ellipse((s * (x - 0.08), s * (y - 0.08), s * (x + 0.08), s * (y + 0.08)), fill=BG_DOT, outline=color, width=lw)
    return _finish(im, size, px)


BG_DOT = (16, 16, 16, 255)
