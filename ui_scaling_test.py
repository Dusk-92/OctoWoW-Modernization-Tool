import tkinter as tk
from tkinter import ttk

import setup_tool_dynamic


class ScalingTestTool(setup_tool_dynamic.ModernWowSetupTool):
    """Temporary UI-only build for validating Windows DPI/display scaling."""

    def __init__(self, root):
        super().__init__(root)

        # UI-only test: preserve every installer behavior and only change how
        # the existing Tk window allocates and exposes its controls.
        root.title("WoW Vanilla 1.12 Modernization Tool [UI Scaling Test]")
        root.resizable(True, True)

        # Reserve the bottom action button before the expandable notebook.
        # This keeps Apply accessible when Windows text/DPI scaling makes the
        # notebook request more vertical space than the original 680x660 size.
        notebook = next(
            (child for child in root.winfo_children() if isinstance(child, ttk.Notebook)),
            None,
        )
        apply_button = getattr(self, "apply_button", None)
        if notebook is not None and apply_button is not None:
            notebook.pack_forget()
            apply_button.pack_forget()
            apply_button.pack(side="bottom", pady=10, fill="x", padx=20)
            notebook.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        root.update_idletasks()

        # Prefer the widgets' requested size when the monitor has room, while
        # keeping a margin so the window remains reachable on smaller displays.
        screen_width = max(1, root.winfo_screenwidth())
        screen_height = max(1, root.winfo_screenheight())
        max_width = max(640, screen_width - 80)
        max_height = max(520, screen_height - 80)

        requested_width = max(680, root.winfo_reqwidth())
        requested_height = max(660, root.winfo_reqheight())
        width = min(requested_width, max_width)
        height = min(requested_height, max_height)

        root.geometry(f"{width}x{height}")
        root.minsize(min(640, max_width), min(520, max_height))


if __name__ == "__main__":
    root = tk.Tk()
    app = ScalingTestTool(root)
    root.mainloop()
