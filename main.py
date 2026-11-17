"""Flowframes + TikTok 60FPS Studio — entry point.  Made by Mords · TikTok: @Mords_69"""
import sys
import traceback


def main() -> int:
    try:
        from gui.main_window import MainWindow
        MainWindow().mainloop()
        return 0
    except Exception:
        msg = traceback.format_exc()
        try:
            from tkinter import messagebox, Tk
            r = Tk(); r.withdraw()
            messagebox.showerror("Startup error", msg[-1500:])
        except Exception:
            print(msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
