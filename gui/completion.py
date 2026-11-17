import customtkinter as ctk

from core.paths import open_file, open_in_file_manager
from . import theme as T


class CompletionPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.data = None
        self.holder = None

    def show(self, data: dict):
        self.data = data
        for w in self.winfo_children():
            w.destroy()
        top = ctk.CTkFrame(self, fg_color="transparent"); top.pack(fill="x", pady=(0, 16))
        badge = ctk.CTkLabel(top, text="✔", width=54, height=54, corner_radius=27, fg_color="#14301F",
                             text_color=T.OK, font=T.font(24, "bold"))
        badge.pack(side="left")
        col = ctk.CTkFrame(top, fg_color="transparent"); col.pack(side="left", padx=14)
        T.label(col, "Processing complete", 24, "bold", anchor="w").pack(anchor="w")
        T.label(col, data["mode"], 13, "normal", T.MUTED, anchor="w").pack(anchor="w")

        c = T.card(self); c.pack(fill="x")
        g = T.InfoGrid(c); g.pack(fill="x", padx=18, pady=18)
        g.set(list(data["rows"].items()))

        btns = ctk.CTkFrame(self, fg_color="transparent"); btns.pack(fill="x", pady=16)
        T.primary_button(btns, "Open Output Folder", lambda: open_in_file_manager(data["path"]), width=200).pack(side="left")
        T.ghost_button(btns, "▶  Play video", lambda: open_file(data["path"]), width=140).pack(side="left", padx=8)
        T.ghost_button(btns, "Back to Dashboard", lambda: self.app.show_page("dashboard"), width=170).pack(side="left")

        if data.get("report"):
            T.heading(self, "VALIDATION REPORT").pack(anchor="w", pady=(4, 6))
            tb = T.textbox(self, height=220); tb.pack(fill="both", expand=True)
            tb.insert("end", data["report"]); tb.configure(state="disabled")

    def on_show(self):
        pass
