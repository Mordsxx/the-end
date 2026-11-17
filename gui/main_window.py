import customtkinter as ctk
from PIL import Image

from core.paths import resource_path
from . import branding as B
from . import icons
from . import theme as T
from .about import AboutPage
from .completion import CompletionPage
from .dashboard import DashboardPage
from .interpolation_ui import InterpolationPage
from .patch_ui import PatchPage
from .settings import SettingsPage

NAV = [("dashboard", "Dashboard"), ("interpolation", "AI Interpolation"), ("patch", "TikTok 60FPS Patch"),
       ("about", "About"), ("settings", "Settings")]


class MainWindow(ctk.CTk):
    def __init__(self):
        T.init()
        super().__init__(fg_color=T.BG)
        self.title(B.APP_NAME)
        self.geometry("1240x800")
        self.minsize(1080, 720)
        self._set_icon()

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar()

        self.content = ctk.CTkScrollableFrame(self, fg_color=T.BG, corner_radius=0,
                                              scrollbar_button_color=T.ELEV, scrollbar_button_hover_color=T.BORDER)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        self.pages = {}
        for key, cls in (("dashboard", DashboardPage), ("interpolation", InterpolationPage), ("patch", PatchPage),
                         ("about", AboutPage), ("settings", SettingsPage)):
            self.pages[key] = cls(self.content, self)
        self.pages["completion"] = CompletionPage(self.content, self)
        self._build_footer()
        self.current = None
        self.show_page("dashboard")

    # -------------------------------------------------------------------------------- chrome
    def _set_icon(self):
        try:
            if self.tk.call("tk", "windowingsystem") == "win32":
                self.iconbitmap(str(resource_path("assets", "icon.ico")))
            else:
                from PIL import ImageTk
                self._icon_ref = ImageTk.PhotoImage(Image.open(resource_path("assets", "icon.png")).resize((64, 64)))
                self.iconphoto(True, self._icon_ref)
        except Exception:
            pass

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=T.BG2, corner_radius=0, width=232, border_width=0)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sb.grid_propagate(False)
        sb.rowconfigure(2, weight=1)
        logo = ctk.CTkFrame(sb, fg_color="transparent"); logo.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 20))
        try:
            im = Image.open(resource_path("assets", "icon.png"))
            ctk.CTkLabel(logo, text="", image=ctk.CTkImage(light_image=im, dark_image=im, size=(44, 44))).pack(side="left")
        except Exception:
            pass
        names = ctk.CTkFrame(logo, fg_color="transparent"); names.pack(side="left", padx=10)
        T.label(names, "Flowframes", 15, "bold", anchor="w").pack(anchor="w")
        T.label(names, "+ TikTok 60FPS Studio", 11, "normal", T.ACCENT_H, anchor="w").pack(anchor="w")

        nav = ctk.CTkFrame(sb, fg_color="transparent"); nav.grid(row=1, column=0, sticky="ew", padx=12)
        self.nav_buttons = {}
        for key, text in NAV:
            b = ctk.CTkButton(nav, text="  " + text, image=icons.nav(key), anchor="w", height=42, corner_radius=10,
                              fg_color="transparent", hover_color=T.ELEV, text_color=T.MUTED, font=T.font(13, "bold"),
                              command=lambda k=key: self.show_page(k))
            b.pack(fill="x", pady=2)
            self.nav_buttons[key] = b

        brand = ctk.CTkFrame(sb, fg_color="transparent"); brand.grid(row=3, column=0, sticky="sew", padx=18, pady=18)
        T.label(brand, B.AUTHOR, 12, "bold", T.TEXT, anchor="w").pack(anchor="w")
        T.label(brand, B.TIKTOK, 12, "normal", T.ACCENT_H, anchor="w").pack(anchor="w")

    def _build_footer(self):
        f = ctk.CTkFrame(self, fg_color=T.BG2, corner_radius=0, height=34, border_width=0)
        f.grid(row=1, column=1, sticky="ew")
        f.grid_propagate(False)
        f.columnconfigure(0, weight=1)
        T.label(f, f"{B.APP_NAME}  ·  v{B.VERSION}", 11, "normal", T.MUTED, anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=6)
        right = ctk.CTkFrame(f, fg_color="transparent"); right.grid(row=0, column=1, sticky="e", padx=18)
        T.label(right, B.AUTHOR, 11, "bold", T.TEXT).pack(side="left", padx=(0, 14))
        T.label(right, B.TIKTOK, 11, "bold", T.ACCENT_H).pack(side="left")

    # -------------------------------------------------------------------------------- navigation
    def show_page(self, key: str):
        if self.current is not None:
            self.pages[self.current].pack_forget()
        self.current = key
        page = self.pages[key]
        page.pack(fill="both", expand=True, padx=30, pady=26)
        for k, b in self.nav_buttons.items():
            active = (k == key)
            b.configure(fg_color=T.ELEV if active else "transparent", text_color=T.TEXT if active else T.MUTED)
        if hasattr(page, "on_show"):
            page.on_show()

    def show_completion(self, summary: dict):
        self.pages["completion"].show(summary)
        self.show_page("completion")
