import json
import os
import tkinter as tk
from tkinter import messagebox, ttk

import dxvk_fps
import setup_tool_dynamic


class ResponsiveModernWowSetupTool(setup_tool_dynamic.ModernWowSetupTool):
    """Production entry point with display-scaling-safe UI and DXVK FPS control."""

    def __init__(self, root):
        # Define these before the parent constructor: WowSetupTool.__init__ calls
        # overridden UI/settings methods while it is still initializing.
        self.detected_refresh_rate = dxvk_fps.detect_max_refresh_rate()
        self.limit_dxvk_fps = tk.BooleanVar(master=root, value=True)
        self.dxvk_fps_limit = tk.IntVar(
            master=root,
            value=self.detected_refresh_rate,
        )
        self.dxvk_fps_checkbox = None
        self.dxvk_fps_entry = None
        self.dxvk_fps_unit_label = None

        super().__init__(root)

        # Keep the FPS controls synchronized when the renderer radio selection
        # changes or when saved settings restore a different renderer.
        self._rendering_mode_trace = self.rendering_mode.trace_add(
            "write",
            lambda *_args: self._update_dxvk_fps_state(),
        )
        self._update_dxvk_fps_state()

        # Preserve all existing installer behavior and only change how the
        # top-level Tk window allocates and exposes its controls.
        root.resizable(True, True)

        # Reserve the bottom action button before the expandable notebook so
        # Windows DPI/text scaling cannot push Apply outside the visible area.
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
        # keeping a margin so the window remains reachable on smaller screens.
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

    def build_main_tab(self, parent):
        super().build_main_tab(parent)

        optional_label = None
        for child in parent.winfo_children():
            try:
                if child.cget("text") == "Optional Mods:":
                    optional_label = child
                    break
            except tk.TclError:
                continue

        fps_frame = ttk.Frame(parent)
        pack_options = {
            "fill": "x",
            "padx": 20,
            "pady": (8, 2),
        }
        if optional_label is not None:
            pack_options["before"] = optional_label
        fps_frame.pack(**pack_options)

        controls = ttk.Frame(fps_frame)
        controls.pack(anchor="w")

        self.dxvk_fps_checkbox = ttk.Checkbutton(
            controls,
            text="Limit DXVK FPS",
            variable=self.limit_dxvk_fps,
            command=self._update_dxvk_fps_state,
        )
        self.dxvk_fps_checkbox.pack(side="left")

        self.dxvk_fps_entry = ttk.Entry(
            controls,
            textvariable=self.dxvk_fps_limit,
            width=7,
        )
        self.dxvk_fps_entry.pack(side="left", padx=(10, 4))

        self.dxvk_fps_unit_label = ttk.Label(controls, text="FPS")
        self.dxvk_fps_unit_label.pack(side="left")

        help_label = ttk.Label(
            fps_frame,
            text=(
                "Auto-detected from the fastest active display at startup. "
                "You can change it manually. DXVK only."
            ),
            font=("Segoe UI", 8, "italic"),
        )
        help_label.pack(anchor="w", padx=(22, 0), pady=(1, 0))

        tooltip = (
            "Limits DXVK with d3d9.maxFrameRate. The initial value uses the "
            f"highest active display refresh rate detected at startup "
            f"({self.detected_refresh_rate} Hz). You can enter another positive "
            "integer. DirectX 9 is never modified by this option."
        )
        setup_tool_dynamic.ToolTip(self.dxvk_fps_checkbox, tooltip)
        setup_tool_dynamic.ToolTip(self.dxvk_fps_entry, tooltip)

        self._update_dxvk_fps_state()

    def _update_dxvk_fps_state(self):
        is_dxvk = getattr(self, "rendering_mode", None) is not None and (
            self.rendering_mode.get() == "dxvk"
        )
        enabled = bool(self.limit_dxvk_fps.get())

        checkbox = getattr(self, "dxvk_fps_checkbox", None)
        entry = getattr(self, "dxvk_fps_entry", None)
        unit_label = getattr(self, "dxvk_fps_unit_label", None)

        if checkbox is not None:
            checkbox.configure(state="normal" if is_dxvk else "disabled")
        if entry is not None:
            entry.configure(state="normal" if is_dxvk and enabled else "disabled")
        if unit_label is not None:
            if is_dxvk and enabled:
                unit_label.state(["!disabled"])
            else:
                unit_label.state(["disabled"])

    def _collect_settings(self):
        settings = super()._collect_settings()
        try:
            fps_value = int(self.dxvk_fps_limit.get())
        except (tk.TclError, TypeError, ValueError):
            fps_value = int(self.detected_refresh_rate)

        settings["dxvk_fps_limit"] = {
            "enabled": bool(self.limit_dxvk_fps.get()),
            "value": fps_value,
        }
        return settings

    def _apply_settings_dict(self, saved):
        super()._apply_settings_dict(saved)

        fps_settings = saved.get("dxvk_fps_limit") if isinstance(saved, dict) else None
        if isinstance(fps_settings, dict):
            enabled = fps_settings.get("enabled")
            value = fps_settings.get("value")
            if isinstance(enabled, bool):
                self.limit_dxvk_fps.set(enabled)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
            ):
                self.dxvk_fps_limit.set(value)

        self._update_dxvk_fps_state()

    def load_settings(self, target_dir):
        # Existing v2.3 installations predate this option. Preserve their
        # current DXVK limit state instead of silently enabling a new cap.
        has_saved_fps_setting = False
        settings_path = self._settings_path(target_dir)
        try:
            with open(settings_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            has_saved_fps_setting = isinstance(
                saved.get("dxvk_fps_limit") if isinstance(saved, dict) else None,
                dict,
            )
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass

        loaded = super().load_settings(target_dir)

        if (
            not has_saved_fps_setting
            and self._looks_like_managed_install(target_dir)
            and self.rendering_mode.get() == "dxvk"
        ):
            existing = dxvk_fps.read_dxvk_fps_limit(
                os.path.join(target_dir, "dxvk.conf")
            )
            if existing is None:
                self.limit_dxvk_fps.set(False)
            else:
                enabled, value = existing
                self.limit_dxvk_fps.set(enabled)
                self.dxvk_fps_limit.set(value)

        self._update_dxvk_fps_state()
        return loaded

    def validate_limits(self):
        if not super().validate_limits():
            return False

        if self.rendering_mode.get() != "dxvk" or not self.limit_dxvk_fps.get():
            return True

        try:
            value = int(self.dxvk_fps_limit.get())
        except (tk.TclError, TypeError, ValueError):
            messagebox.showerror(
                "Input Error",
                "DXVK FPS Limit must contain a positive whole number.",
            )
            return False

        if value <= 0:
            messagebox.showerror(
                "Input Error",
                "DXVK FPS Limit must be greater than 0.",
            )
            return False

        return True

    def configure_dxvk(self, target):
        super().configure_dxvk(target)

        # DirectX 9 follows the existing renderer cleanup path above. Never
        # create or modify dxvk.conf when DXVK is not selected.
        if self.rendering_mode.get() != "dxvk":
            return

        dxvk_fps.apply_dxvk_fps_limit(
            os.path.join(target, "dxvk.conf"),
            bool(self.limit_dxvk_fps.get()),
            int(self.dxvk_fps_limit.get()),
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = ResponsiveModernWowSetupTool(root)
    root.mainloop()
