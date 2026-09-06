import os
import hashlib
import sys
import json
import shutil
import subprocess
import math
import re
import secrets
import stat
import struct
import tkinter as tk
import webbrowser
from tkinter import ttk, filedialog, messagebox

import remote_packages

try:
    import winreg
except ImportError:
    # Keeps the module importable by non-Windows test runners. The application
    # itself targets Windows, and AutoLogin encryption setup validates this.
    winreg = None

def get_base_path():
    """Gets the correct directory whether running as a script or a compiled .exe"""
    if getattr(sys, 'frozen', False):
        # Running as a compiled PyInstaller executable
        return sys._MEIPASS
    # Running as a normal Python script
    return os.path.dirname(os.path.abspath(__file__))

class ToolTip:
    """Creates a hover-tooltip for a given tkinter widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(400, self.showtip) # 400ms delay before showing

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def showtip(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("Segoe UI", "9", "normal"), wraplength=350)
        label.pack(ipadx=6, ipady=4)

    def leave(self, event=None):
        self.unschedule()
        if self.tw:
            self.tw.destroy()
            self.tw = None

class WowSetupTool:
    def __init__(self, root):
        self.root = root
        self.root.title("WoW Vanilla 1.12 Modernization Tool")
        
        # Lock window size exactly as requested
        self.root.geometry("680x660") 
        self.root.resizable(False, False)

        icon_path = os.path.join(get_base_path(), "PurpleWowLogo.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # Dictionary containing all tooltip explanations
        self.descriptions = {
            # Setup & General
            "autologin": "Adds saved account/character shortcuts to the login screen. When AutoLogin and Nampower are enabled together, the tool automatically creates or reuses the Windows user encryption key required by Nampower so saved passwords can be encrypted.",
            "render_directx9": "Uses VanillaFixes with the game's native DirectX 9 renderer. Existing d3d9.dll/dxvk.conf proxy files are moved to a Modernization Tool backup so they cannot keep DXVK or another D3D9 wrapper active.",
            "render_dxvk": "Uses VanillaFixes with DXVK, translating DirectX 9 to Vulkan for smoother frame pacing on many modern systems.",

            # Core DLLs
            "nampower.dll": "Improves spell input responsiveness by adding modern spell queueing and latency compensation to the Vanilla client.",
            "no1600x1200.dll": "Removes the hardcoded 1600x1200 resolution limit. Natively unlocks widescreen and ultrawidescreen resolutions in the game settings.",
            "perf_boost.dll": "Provides dynamic render distance controls (culling). Stabilizes framerates in crowded environments by lowering the rendering priority of non-essential entities.",
            "UnitXP_SP3.dll": "Engine-level optimizations replacing legacy assembly. Introduces improved network handling, better Tab-targeting, true line-of-sight checks via Lua, and modern nameplate support.",
            "VanillaHelpers.dll": "Expands engine limits. Raises the client memory allocator from 2GB to 4GB to prevent Out-of-Memory crashes and introduces modern high-resolution texture support.",
            "SuperWoWhook.dll": "Injects a massively expanded Lua API. Increases macro limit, enables castbars on nameplates, and provides hooks for modern UI addons.",
            "transmogfix.dll": "Eliminates FPS drops caused by rapid equipment visual updates when transmogged items lose durability.",
            "weirdperformance.dll": "Engine-level optimizations: SIMD math replacements, faster data decompression (modern zlib), MPQ file caching, timer calibration, and Lua runtime GC improvements.",

            # WeirdUtils
            "bigcursor.dll": "Upscales the hardware cursor for improved visibility on modern resolutions without losing sharpness (up to 4.0x scale via CVar).",
            "customassets.dll": "Enables loading loose game asset files from the Data/ directory mirroring internal paths without needing to repack MPQ archives.",
            "logsessions.dll": "Organizes combat and chat logs into clean, per-character, per-day files automatically upon login.",
            "minimapicons.dll": "Adds TBC/WotLK-style minimap tracking icons for NPCs and objects, combined into a new native tracking dropdown.",
            "pngscreenshots.dll": "Saves screenshots as compressed PNG files on a background thread to completely eliminate frame drops when taking pictures.",
            "worldmarkers.dll": "Place up to 5 animated colored markers (Cataclysm style) in the world for raid positioning. Syncs automatically with other users.",
            "WowPresence.dll": "Shows your WoW character activity on Discord using WowPresence by Dusk-92. Modernization Tool downloads and updates WowPresence from its GitHub releases, stores its configuration and status under .modernization_tool\\WowPresence, and preconfigures the OctoWoW Discord Application ID. Advanced users can change .modernization_tool\\WowPresence\\discord_application_id for another Discord application. If Discord runs as administrator, WoW must also run as administrator for Rich Presence to work.",

            # Tweaks Tab
            "fov": "Calculates horizontal Field of View mathematically scaled to maintain vertical aspect space based on your screen ratio.",
            "farclip": "Sets the active terrain render distance used by the game. Vanilla default is 777. The Tool keeps the executable Farclip ceiling fixed at 3000.",
            "frill": "Changes the ground clutter (grass) render distance. Vanilla default is 70. Tweaks default is 300.",
            "nameplate": "Increases the distance at which enemy nameplates become visible. Vanilla default is 20. Tweaks default is 41.",
            "cam": "Increases the maximum camera zoom-out distance. Vanilla default is 50. Max safe limit is 100.",
            "sound": "Increases the maximum number of simultaneous audio channels. Values above 64 may cause crashes.",
            "loot": "Reverses the auto-loot behavior so you always auto-loot, and hold Shift for manual looting.",
            "bg_sound": "Allows game sounds to continue playing while the game is minimized or in the background.",
            "laa": "Patches the executable to be Large Address Aware, allowing the 32-bit client to utilize up to 4GB of RAM (Essential for HD Mods).",
            "cam_fix": "Fixes a bug where right-clicking and dragging to rotate the camera occasionally snaps your view in a random direction.",
            "dep_fix": "Disables Data Execution Prevention (DEP) and EmulateAtlThunks for WoW_Modernized.exe. Prevents Windows from force-closing the game due to memory hooks. (Prompts for Admin Privileges).",
            "script_memory": "Sets WoW's AddOn Script Memory to 0 (unlimited). When disabled, the tool leaves your existing Config.wtf value unchanged.",
            "crossfaction_res": "Allows the client to attempt resurrection of released cross-faction players.",
            "custom_glues": "Enables custom GlueXML frames and XML on the login and character-selection screens.",
            "bluemoon": "Restores the rare blue moon visual effect that appears around 1 AM on some nights. Installed as a patch inside WoW_Modernized.exe by vanilla-tweaks (no MPQ).",
            "clear_wdb": "Automatically clears the current WDB cache and prevents stale WDB data from rebuilding by placing an empty WDB blocker file in the game folder. Unchecking this option removes the blocker so WoW can create its WDB folder normally.",
            "darker_nights": "Installs Project Reforged Patch-N for darker, more atmospheric nights. Installed file: Data\\patch-N.mpq. Project Reforged recommends VanillaHelpers.",
            "pretty_night_sky": "Replaces the Vanilla night sky with a more detailed starry sky. Installed file: Data\\patch-Z.mpq. The original hosted patch-9 name is deliberately changed so the official numeric patch-9.mpq is never overwritten.",
            "epoch_water": "Replaces Vanilla water textures with the Epoch Water visual pack. Installed file: Data\\patch-W.mpq.",
            "fog_pushback": "Pushes environmental fog farther back for a clearer long-distance view. Installed file: Data\\patch-Y.mpq. Works best together with an increased Farclip value.",
            "pink_herbs": "Turns most herb-node textures bright pink/purple to make gathering nodes easier to spot. Installed file: Data\\patch-V.mpq. The patch-V name avoids conflicts with other visual packs that use patch-H.mpq.",
            "no_error_sounds": "Installs the complete NoErrorSounds pack: muted spell fizzle sounds plus its included muted interface sounds. Installed as loose WAV files under Sound\\Spells\\Fizzle and Sound\\interface (no MPQ).",
            "fish_ping": "Replaces the fishing bite sound with a much more noticeable ping. Installed file: Sound\\Spells\\Tradeskills\\FishBite.wav (no MPQ). Designed specifically for WoW Vanilla 1.12.1.",
            "warlock_muted_demons": "Mutes the repeated voice lines from Warlock demons using Vanilla-compatible loose sound replacements. Installed as loose WAV files under Data\\Sound\\Creature (no MPQ)."
        }

        # Basic Setup Variables
        self.wow_dir = tk.StringVar()
        self.rendering_mode = tk.StringVar(value="directx9")
        self.install_autologin = tk.BooleanVar(value=True)

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.detected_ratio = self.screen_w / self.screen_h

        self.ratio_options = {
            f"Auto-detected ({self.screen_w}x{self.screen_h})": self.detected_ratio,
            "4:3 (Standard)": 4.0/3.0,
            "16:9 (Widescreen)": 16.0/9.0,
            "16:10 (Widescreen)": 16.0/10.0,
            "21:9 (Ultrawide)": 21.0/9.0,
            "32:9 (Super Ultrawide)": 32.0/9.0
        }

        # Recommended core plugins, kept in the same order as the UI.
        self.core_plugins = {
            "nampower.dll": tk.BooleanVar(value=True),
            "UnitXP_SP3.dll": tk.BooleanVar(value=True),
            "SuperWoWhook.dll": tk.BooleanVar(value=True),
            "transmogfix.dll": tk.BooleanVar(value=True),
            "perf_boost.dll": tk.BooleanVar(value=True),
            "weirdperformance.dll": tk.BooleanVar(value=True),
            "VanillaHelpers.dll": tk.BooleanVar(value=True)
        }

        # Optional client fixes and WeirdUtils.
        self.optional_plugins = {
            "no1600x1200.dll": tk.BooleanVar(value=False),
            "bigcursor.dll": tk.BooleanVar(value=False),
            "customassets.dll": tk.BooleanVar(value=False),
            "logsessions.dll": tk.BooleanVar(value=False),
            "minimapicons.dll": tk.BooleanVar(value=False),
            "pngscreenshots.dll": tk.BooleanVar(value=False),
            "worldmarkers.dll": tk.BooleanVar(value=False),
            "WowPresence.dll": tk.BooleanVar(value=False)
        }

        self.addon_dependencies = {
            "nampower.dll": "nampowersettings",
            "perf_boost.dll": "perfboostsettings",
            "UnitXP_SP3.dll": "UnitXP_SP3_Addon",
            "SuperWoWhook.dll": "SuperAPI"
        }

        # Vanilla Tweaks Variables 
        self.vt_fov = tk.DoubleVar()
        self.ratio_var = tk.StringVar(value=list(self.ratio_options.keys())[0]) 
        self.vt_farclip = tk.IntVar(value=777)
        self.vt_frill = tk.IntVar(value=300)
        self.vt_nameplate = tk.IntVar(value=41)
        self.vt_soundchan = tk.IntVar(value=64)
        self.vt_maxcam = tk.IntVar(value=100)
        
        # Tweak Toggles 
        self.vt_quickloot = tk.BooleanVar(value=True)
        self.vt_bg_sound = tk.BooleanVar(value=True)
        self.vt_laa = tk.BooleanVar(value=True)
        self.vt_cam_fix = tk.BooleanVar(value=True)
        self.vt_dep_fix = tk.BooleanVar(value=True)
        self.vt_script_memory = tk.BooleanVar(value=True)
        self.vt_crossfaction_res = tk.BooleanVar(value=False)
        self.vt_custom_glues = tk.BooleanVar(value=True)
        self.vt_bluemoon = tk.BooleanVar(value=False)
        self.vt_clear_wdb = tk.BooleanVar(value=True)

        # Optional visual and audio mods.
        self.visual_mods = {
            "darker_nights": tk.BooleanVar(value=False),
            "pretty_night_sky": tk.BooleanVar(value=False),
            "epoch_water": tk.BooleanVar(value=False),
            "fog_pushback": tk.BooleanVar(value=False),
            "pink_herbs": tk.BooleanVar(value=False),
        }
        self.audio_mods = {
            "no_error_sounds": tk.BooleanVar(value=False),
            "fish_ping": tk.BooleanVar(value=False),
            "warlock_muted_demons": tk.BooleanVar(value=False),
        }
        
        # Safety Limit Toggle
        self.safety_override = tk.BooleanVar(value=False)
        self.slider_widgets =[] 

        self._loaded_settings_dir = None
        self._loading_settings = False
        self._install_in_progress = False

        self.on_ratio_change() 
        self.build_ui()

        # Snapshot the clean application defaults after every variable and
        # subclass-provided option exists. Each WoW folder is loaded from this
        # baseline so settings from one installation cannot leak into another.
        self._default_settings = self._collect_settings()

        # Settings are stored per WoW installation. Loading on path selection
        # means a newer copy of the tool can immediately restore the choices
        # made by an older copy.
        self.wow_dir.trace_add("write", self._on_wow_dir_changed)

    def on_ratio_change(self, event=None):
        selection = self.ratio_var.get()
        ratio = self.ratio_options.get(selection, 4.0/3.0)
        default_ar, default_fov = 4.0 / 3.0, 1.570796
        fov = 2 * math.atan((ratio / default_ar) * math.tan(default_fov / 2))
        self.vt_fov.set(round(fov, 4))

    def toggle_safety_limits(self):
        override = self.safety_override.get()
        for scale, safe_max, extreme_max, var in self.slider_widgets:
            if override:
                scale.configure(to=extreme_max)
            else:
                scale.configure(to=safe_max)
                try:
                    if var.get() > safe_max:
                        var.set(safe_max)
                except tk.TclError:
                    pass

    def create_slider_row(self, parent, row, label_text, var, min_val, safe_max, extreme_max, desc_key):
        lbl = ttk.Label(parent, text=label_text)
        lbl.grid(row=row, column=0, sticky='w', pady=5)
        ToolTip(lbl, self.descriptions[desc_key])
        
        current_max = extreme_max if self.safety_override.get() else safe_max

        scale = ttk.Scale(parent, from_=min_val, to=current_max, orient='horizontal', variable=var,
                          command=lambda s, v=var: v.set(int(float(s))))
        scale.grid(row=row, column=1, sticky='ew', padx=15, pady=5)
        
        entry = ttk.Entry(parent, textvariable=var, width=8)
        entry.grid(row=row, column=2, sticky='e', pady=5)

        self.slider_widgets.append((scale, safe_max, extreme_max, var))
        return lbl, scale, entry

    def create_mod_option_row(self, parent, text, variable, attribution, tooltip):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=10, pady=4)

        cb = ttk.Checkbutton(row, text=text, variable=variable)
        cb.pack(side="left")
        ToolTip(cb, tooltip)

        if attribution:
            ttk.Label(
                row,
                text=attribution,
                font=("Segoe UI", 7, "italic"),
            ).pack(side="right", padx=(6, 0))
        return cb


    def _settings_path(self, target_dir):
        return os.path.join(target_dir, ".modernization_tool", "settings.json")

    def _looks_like_managed_install(self, target_dir):
        return any(
            os.path.exists(os.path.join(target_dir, rel))
            for rel in (
                "WoW_Modernized.exe",
                "Play Modernized WoW.lnk",
                ".modernization_tool",
            )
        )

    def _collect_settings(self):
        live_plugins = {}
        for name in (
            "classicapi_enabled",
            "auction_throttle_enabled",
            "vmmfix_enabled",
            "interact_enabled",
        ):
            var = getattr(self, name, None)
            if var is not None:
                live_plugins[name] = bool(var.get())

        return {
            "version": 1,
            "rendering_mode": self.rendering_mode.get(),
            "install_autologin": bool(self.install_autologin.get()),
            "core_plugins": {
                name: bool(var.get()) for name, var in self.core_plugins.items()
            },
            "optional_plugins": {
                name: bool(var.get()) for name, var in self.optional_plugins.items()
            },
            "live_plugins": live_plugins,
            "vanilla_tweaks": {
                "ratio": self.ratio_var.get(),
                "fov": float(self.vt_fov.get()),
                "farclip": int(self.vt_farclip.get()),
                "frill": int(self.vt_frill.get()),
                "nameplate": int(self.vt_nameplate.get()),
                "sound_channels": int(self.vt_soundchan.get()),
                "max_camera": int(self.vt_maxcam.get()),
                "quickloot": bool(self.vt_quickloot.get()),
                "background_sound": bool(self.vt_bg_sound.get()),
                "laa": bool(self.vt_laa.get()),
                "camera_fix": bool(self.vt_cam_fix.get()),
                "dep_fix": bool(self.vt_dep_fix.get()),
                "script_memory": bool(self.vt_script_memory.get()),
                "crossfaction_res": bool(self.vt_crossfaction_res.get()),
                "custom_glues": bool(self.vt_custom_glues.get()),
                "bluemoon": bool(self.vt_bluemoon.get()),
                "clear_wdb": bool(self.vt_clear_wdb.get()),
                "safety_override": bool(self.safety_override.get()),
            },
            "visual_mods": {
                name: bool(var.get()) for name, var in self.visual_mods.items()
            },
            "audio_mods": {
                name: bool(var.get()) for name, var in self.audio_mods.items()
            },
        }

    def save_settings(self, target_dir):
        settings_path = self._settings_path(target_dir)
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        temp_path = settings_path + ".new"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(self._collect_settings(), handle, indent=2, sort_keys=True)
        os.replace(temp_path, settings_path)
        self._loaded_settings_dir = os.path.normcase(os.path.abspath(target_dir))

    def _set_bool_mapping(self, saved, variables):
        if not isinstance(saved, dict):
            return
        for name, value in saved.items():
            var = variables.get(name)
            if var is not None and isinstance(value, bool):
                var.set(value)

    def _load_legacy_install_state(self, target_dir):
        """Best-effort migration for installs made before settings.json existed."""
        if not self._looks_like_managed_install(target_dir):
            return

        if (
            os.path.isfile(os.path.join(target_dir, "d3d9.dll"))
            and os.path.isfile(os.path.join(target_dir, "dxvk.conf"))
        ):
            self.rendering_mode.set("dxvk")
        else:
            self.rendering_mode.set("directx9")

        # Once this tool has clearly been used on the folder, on-disk presence
        # is the safest migration signal for plugin checkboxes.
        for filename, var in self.core_plugins.items():
            var.set(os.path.isfile(os.path.join(target_dir, filename)))

        for filename, var in self.optional_plugins.items():
            var.set(os.path.isfile(os.path.join(target_dir, filename)))

        live_files = {
            "classicapi_enabled": "ClassicAPI.dll",
            "auction_throttle_enabled": "AuctionQueryThrottle.dll",
            "vmmfix_enabled": "VanillaMultiMonitorFix.dll",
            "interact_enabled": "Interact.dll",
        }
        for attr, filename in live_files.items():
            var = getattr(self, attr, None)
            if var is not None:
                var.set(os.path.isfile(os.path.join(target_dir, filename)))

        autologin_lua = os.path.join(
            target_dir, "Data", "Interface", "GlueXML", "AutoLogin.lua"
        )
        self.install_autologin.set(os.path.isfile(autologin_lua))

        managed_ids = {
            "darker_nights": "visual_darker_nights",
            "pretty_night_sky": "visual_pretty_night_sky",
            "epoch_water": "visual_epoch_water",
            "fog_pushback": "visual_fog_pushback",
            "pink_herbs": "visual_pink_herbs",
        }
        for key, managed_id in managed_ids.items():
            self.visual_mods[key].set(
                remote_packages.managed_mod_is_installed(target_dir, managed_id)
            )

        managed_audio = {
            "no_error_sounds": "audio_no_error_sounds",
            "fish_ping": "audio_fish_ping",
            "warlock_muted_demons": "audio_warlock_muted_demons",
        }
        for key, managed_id in managed_audio.items():
            self.audio_mods[key].set(
                remote_packages.managed_mod_is_installed(target_dir, managed_id)
            )

        wdb_path = os.path.join(target_dir, "WDB")
        if os.path.isfile(wdb_path):
            self.vt_clear_wdb.set(True)
        elif os.path.isdir(wdb_path):
            self.vt_clear_wdb.set(False)

    def _apply_settings_dict(self, saved):
        if not isinstance(saved, dict):
            raise ValueError("settings root must be a JSON object")

        rendering = saved.get("rendering_mode")
        if rendering in ("directx9", "dxvk"):
            self.rendering_mode.set(rendering)

        if isinstance(saved.get("install_autologin"), bool):
            self.install_autologin.set(saved["install_autologin"])

        self._set_bool_mapping(saved.get("core_plugins"), self.core_plugins)
        self._set_bool_mapping(saved.get("optional_plugins"), self.optional_plugins)
        self._set_bool_mapping(saved.get("visual_mods"), self.visual_mods)
        self._set_bool_mapping(saved.get("audio_mods"), self.audio_mods)

        live = saved.get("live_plugins")
        if isinstance(live, dict):
            for name, value in live.items():
                var = getattr(self, name, None)
                if var is not None and isinstance(value, bool):
                    var.set(value)

        tweaks = saved.get("vanilla_tweaks")
        if isinstance(tweaks, dict):
            ratio = tweaks.get("ratio")
            if isinstance(ratio, str) and ratio in self.ratio_options:
                self.ratio_var.set(ratio)

            numeric = (
                ("fov", self.vt_fov, float),
                ("farclip", self.vt_farclip, int),
                ("frill", self.vt_frill, int),
                ("nameplate", self.vt_nameplate, int),
                ("sound_channels", self.vt_soundchan, int),
                ("max_camera", self.vt_maxcam, int),
            )
            for key, var, converter in numeric:
                value = tweaks.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    var.set(converter(value))

            boolean = (
                ("quickloot", self.vt_quickloot),
                ("background_sound", self.vt_bg_sound),
                ("laa", self.vt_laa),
                ("camera_fix", self.vt_cam_fix),
                ("dep_fix", self.vt_dep_fix),
                ("script_memory", self.vt_script_memory),
                ("crossfaction_res", self.vt_crossfaction_res),
                ("custom_glues", self.vt_custom_glues),
                ("bluemoon", self.vt_bluemoon),
                ("clear_wdb", self.vt_clear_wdb),
                ("safety_override", self.safety_override),
            )
            for key, var in boolean:
                value = tweaks.get(key)
                if isinstance(value, bool):
                    var.set(value)

    def _reset_settings_to_defaults(self):
        defaults = getattr(self, "_default_settings", None)
        if isinstance(defaults, dict):
            self._apply_settings_dict(defaults)

    def _normalize_plugin_conflicts(self):
        """Resolve impossible states created by old/corrupt settings files."""
        no1600 = self.optional_plugins.get("no1600x1200.dll")
        vmmfix = getattr(self, "vmmfix_enabled", None)
        if no1600 is not None and vmmfix is not None and no1600.get() and vmmfix.get():
            # VMMFix is the more complete monitor/resolution fix. Prefer it when
            # legacy state incorrectly claims both mutually exclusive options.
            no1600.set(False)
            return True
        return False

    def validate_plugin_conflicts(self):
        """Last-line safety check independent of checkbox callbacks/settings."""
        no1600 = self.optional_plugins.get("no1600x1200.dll")
        vmmfix = getattr(self, "vmmfix_enabled", None)
        if no1600 is not None and vmmfix is not None and no1600.get() and vmmfix.get():
            messagebox.showerror(
                "Plugin conflict",
                "no1600x1200 and VanillaMultiMonitorFix cannot be enabled together.\n\n"
                "Disable one of them before applying the setup.",
            )
            return False

        return True

    def load_settings(self, target_dir):
        settings_path = self._settings_path(target_dir)
        self._loading_settings = True
        recovered_from_damage = False

        try:
            # Always start from clean defaults. This prevents values from a
            # previously selected WoW directory leaking into this installation.
            self._reset_settings_to_defaults()

            if not os.path.isfile(settings_path):
                self._load_legacy_install_state(target_dir)
                self._normalize_plugin_conflicts()
                self.toggle_safety_limits()
                return False

            try:
                with open(settings_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                if not isinstance(saved, dict):
                    raise ValueError("settings root must be a JSON object")
                self._apply_settings_dict(saved)
            except (OSError, json.JSONDecodeError, ValueError, TypeError, tk.TclError):
                # Keep the damaged file untouched for manual recovery/debugging.
                # Recover only what can safely be inferred from the WoW folder.
                self._reset_settings_to_defaults()
                self._load_legacy_install_state(target_dir)
                recovered_from_damage = True

            self._normalize_plugin_conflicts()
            self.toggle_safety_limits()

            if recovered_from_damage:
                messagebox.showwarning(
                    "Settings recovery",
                    "The saved Modernization Tool settings for this WoW folder could not be read.\n\n"
                    "The file was left untouched. Installed components were detected where possible, "
                    "and defaults were used for options that cannot be inferred. Review the choices "
                    "before clicking Apply.",
                )
                return False

            return True
        finally:
            self._loading_settings = False

    def _on_wow_dir_changed(self, *_args):
        if self._loading_settings:
            return

        target_dir = self.wow_dir.get().strip()
        if not target_dir:
            return

        normalized = os.path.normcase(os.path.abspath(target_dir))
        if normalized == self._loaded_settings_dir:
            return

        # Do not pop validation errors while the user is typing a path.
        if not (
            os.path.isfile(os.path.join(target_dir, "WoW.exe"))
            and os.path.isdir(os.path.join(target_dir, "Data"))
        ):
            return

        self.load_settings(target_dir)
        self._loaded_settings_dir = normalized

    def build_ui(self):
        help_banner = tk.Label(
            self.root,
            text="💡  HOVER FOR HELP — Move your mouse over any setting or plugin to see what it does.",
            background="#EAF4FF",
            foreground="#005A9E",
            font=("Segoe UI", 10, "bold"),
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=6,
        )
        help_banner.pack(fill="x", padx=10, pady=(8, 2))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        tab_main = ttk.Frame(notebook)
        tab_plugins = ttk.Frame(notebook)
        tab_tweaks = ttk.Frame(notebook)
        tab_visual_audio = ttk.Frame(notebook)
        tab_credits = ttk.Frame(notebook)

        notebook.add(tab_main, text="Setup & Rendering")
        notebook.add(tab_plugins, text="Plugins")
        notebook.add(tab_tweaks, text="Vanilla Tweaks")
        notebook.add(tab_visual_audio, text="Visual & Audio")
        notebook.add(tab_credits, text="Credits & Sources")

        self.build_main_tab(tab_main)
        self.build_plugins_tab(tab_plugins)
        self.build_tweaks_tab(tab_tweaks)
        self.build_visual_audio_tab(tab_visual_audio)
        self.build_credits_tab(tab_credits)

        self.apply_button = ttk.Button(
            self.root,
            text="Apply Setup & Tweaks",
            command=self.run_installation,
            style="Accent.TButton",
        )
        self.apply_button.pack(pady=10, fill='x', padx=20)

    def build_main_tab(self, parent):
        ttk.Label(parent, text="Vanilla 1.12 Installation Directory:").pack(anchor='w', pady=(10, 0), padx=10)
        dir_frame = ttk.Frame(parent)
        dir_frame.pack(fill='x', padx=10, pady=5)
        ttk.Entry(dir_frame, textvariable=self.wow_dir).pack(side='left', fill='x', expand=True)
        ttk.Button(dir_frame, text="Browse...", command=lambda: self.wow_dir.set(filedialog.askdirectory())).pack(side='left', padx=(5,0))

        ttk.Label(parent, text="Rendering Mode:").pack(anchor='w', pady=(20, 0), padx=10)
        
        rb_directx9 = ttk.Radiobutton(
            parent,
            text="VanillaFixes (DirectX 9)",
            variable=self.rendering_mode,
            value="directx9"
        )
        rb_directx9.pack(anchor='w', padx=20, pady=2)
        ToolTip(rb_directx9, self.descriptions["render_directx9"])

        rb_dxvk = ttk.Radiobutton(
            parent,
            text="VanillaFixes + DXVK (Vulkan)",
            variable=self.rendering_mode,
            value="dxvk"
        )
        rb_dxvk.pack(anchor='w', padx=20, pady=2)
        ToolTip(rb_dxvk, self.descriptions["render_dxvk"])

        ttk.Label(parent, text="Optional Mods:").pack(anchor='w', pady=(20, 0), padx=10)
        
        cb_login = ttk.Checkbutton(
            parent,
            text="Install Auto Login Mod (Data/Interface/GlueXML)",
            variable=self.install_autologin,
        )
        cb_login.pack(anchor='w', padx=20, pady=2)
        ToolTip(cb_login, self.descriptions["autologin"])

        autologin_warning = tk.Label(
            parent,
            text=(
                "🔒 With Nampower enabled, the tool automatically prepares password "
                "encryption for AutoLogin. Existing encryption keys are never replaced."
            ),
            justify="left",
            anchor="w",
            wraplength=610,
            foreground="#8A4B00",
            font=("Segoe UI", 8, "italic"),
        )
        autologin_warning.pack(anchor="w", padx=38, pady=(1, 0))
        ToolTip(autologin_warning, self.descriptions["autologin"])

    def build_plugins_tab(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill='both', expand=True, padx=10, pady=10)

        left_frame = ttk.LabelFrame(container, text="Recommended Core")
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        ttk.Label(left_frame, text="These are highly recommended for performance\nand client stability.", font=("", 8, "italic")).pack(anchor='w', padx=10, pady=10)
        
        for dll, var in self.core_plugins.items():
            cb = ttk.Checkbutton(left_frame, text=dll, variable=var)
            cb.pack(anchor='w', padx=10, pady=4)
            ToolTip(cb, self.descriptions.get(dll, "")) 

        right_frame = ttk.LabelFrame(container, text="Optional")
        right_frame.pack(side='right', fill='both', expand=True, padx=(5, 0))

        ttk.Label(right_frame, text="Optional client-side fixes and quality-of-life enhancements.", font=("", 8, "italic")).pack(anchor='w', padx=10, pady=10)
        
        for dll, var in self.optional_plugins.items():
            cb = ttk.Checkbutton(right_frame, text=dll, variable=var)
            cb.pack(anchor='w', padx=10, pady=4)
            ToolTip(cb, self.descriptions.get(dll, "")) 

    def build_tweaks_tab(self, parent):
        fov_frame = ttk.LabelFrame(parent, text="Field of View (FoV) Calculator")
        fov_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(fov_frame, text="Screen Aspect Ratio:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.fov_ratio_combo = ttk.Combobox(
            fov_frame,
            textvariable=self.ratio_var,
            values=list(self.ratio_options.keys()),
            state="readonly",
            width=28
        )
        self.fov_ratio_combo.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        self.fov_ratio_combo.bind("<<ComboboxSelected>>", self.on_ratio_change)

        fov_lbl = ttk.Label(fov_frame, text="Calculated FoV (Radians) [Safe Max: 2.268]:")
        fov_lbl.grid(row=1, column=0, padx=5, pady=5, sticky='w')
        ToolTip(fov_lbl, self.descriptions["fov"])
        
        self.fov_entry = ttk.Entry(fov_frame, textvariable=self.vt_fov, width=15)
        self.fov_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        style = ttk.Style()
        style.configure("Warning.TCheckbutton", foreground="red")
        ttk.Checkbutton(parent, text="Disable Safety Limits (Warning: Exceeding max limits may cause game instability)", 
                        variable=self.safety_override, style="Warning.TCheckbutton",
                        command=self.toggle_safety_limits).pack(anchor='w', padx=15, pady=(0, 5))

        frame_nums = ttk.Frame(parent)
        frame_nums.pack(fill='x', padx=15, pady=0)
        frame_nums.columnconfigure(1, weight=1) 
        
        self.create_slider_row(frame_nums, 0, "Render distance (Farclip) [Safe Max: 1500]:", self.vt_farclip, 777, 1500, 3000, "farclip")
        self.create_slider_row(frame_nums, 1, "Ground clutter (Frilldistance) [Safe Max: 300]:", self.vt_frill, 70, 300, 1000, "frill")
        self.create_slider_row(frame_nums, 2, "Nameplate range [Safe Max: 41]:", self.vt_nameplate, 20, 41, 150, "nameplate")
        self.create_slider_row(frame_nums, 3, "Camera distance [Safe Max: 100]:", self.vt_maxcam, 50, 100, 250, "cam")
        _, self.sound_scale, self.sound_entry = self.create_slider_row(
            frame_nums, 4, "Sound Channels [Safe Max: 64]:",
            self.vt_soundchan, 12, 64, 128, "sound"
        )

        ttk.Label(parent, text="Patch Toggles:").pack(anchor='w', pady=(5,0), padx=10)
        
        toggles_frame = ttk.Frame(parent)
        toggles_frame.pack(fill='x', padx=10)
        
        self.cb_loot = ttk.Checkbutton(toggles_frame, text="Always auto-loot", variable=self.vt_quickloot)
        self.cb_loot.grid(row=0, column=0, sticky='w', padx=10, pady=2)
        ToolTip(self.cb_loot, self.descriptions["loot"])

        self.cb_bg = ttk.Checkbutton(toggles_frame, text="Background sounds", variable=self.vt_bg_sound)
        self.cb_bg.grid(row=0, column=1, sticky='w', padx=10, pady=2)
        ToolTip(self.cb_bg, self.descriptions["bg_sound"])
        
        cb_laa = ttk.Checkbutton(toggles_frame, text="Large Address Aware (LAA)", variable=self.vt_laa)
        cb_laa.grid(row=1, column=0, sticky='w', padx=10, pady=2)
        ToolTip(cb_laa, self.descriptions["laa"])
        
        cb_cam = ttk.Checkbutton(toggles_frame, text="Fix Camera Skip Glitch", variable=self.vt_cam_fix)
        cb_cam.grid(row=1, column=1, sticky='w', padx=10, pady=2)
        ToolTip(cb_cam, self.descriptions["cam_fix"])

        cb_dep = ttk.Checkbutton(toggles_frame, text="Disable DEP (Requires Admin)", variable=self.vt_dep_fix)
        cb_dep.grid(row=2, column=0, sticky='w', padx=10, pady=2)
        ToolTip(cb_dep, self.descriptions["dep_fix"])

        cb_script_memory = ttk.Checkbutton(
            toggles_frame,
            text="Unlimited AddOn Script Memory",
            variable=self.vt_script_memory
        )
        cb_script_memory.grid(row=2, column=1, sticky='w', padx=10, pady=2)
        ToolTip(cb_script_memory, self.descriptions["script_memory"])

        cb_crossfaction = ttk.Checkbutton(
            toggles_frame,
            text="Cross-faction Res Fix",
            variable=self.vt_crossfaction_res
        )
        cb_crossfaction.grid(row=3, column=0, sticky='w', padx=10, pady=2)
        ToolTip(cb_crossfaction, self.descriptions["crossfaction_res"])

        cb_custom_glues = ttk.Checkbutton(
            toggles_frame,
            text="Custom Glues Patch",
            variable=self.vt_custom_glues
        )
        cb_custom_glues.grid(row=3, column=1, sticky='w', padx=10, pady=2)
        ToolTip(cb_custom_glues, self.descriptions["custom_glues"])

        cb_clear_wdb = ttk.Checkbutton(
            toggles_frame,
            text="Automatically Clear WDB",
            variable=self.vt_clear_wdb
        )
        cb_clear_wdb.grid(row=4, column=0, sticky='w', padx=10, pady=2)
        ToolTip(cb_clear_wdb, self.descriptions["clear_wdb"])


    def build_visual_audio_tab(self, parent):
        ttk.Label(
            parent,
            text="Optional appearance and sound replacements. Everything here is disabled by default.",
            font=("Segoe UI", 9, "italic"),
        ).pack(anchor="w", padx=12, pady=(10, 6))

        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        visual_frame = ttk.LabelFrame(container, text="Visual Mods")
        visual_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        audio_frame = ttk.LabelFrame(container, text="Audio Mods")
        audio_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        self.create_mod_option_row(
            visual_frame,
            "Bluemoon Patch",
            self.vt_bluemoon,
            "via vanilla-tweaks",
            self.descriptions["bluemoon"],
        )
        self.create_mod_option_row(
            visual_frame,
            "Darker Nights",
            self.visual_mods["darker_nights"],
            "by Project Reforged",
            self.descriptions["darker_nights"],
        )
        self.create_mod_option_row(
            visual_frame,
            "Pretty Night Sky",
            self.visual_mods["pretty_night_sky"],
            "source: RetroCro",
            self.descriptions["pretty_night_sky"],
        )
        self.create_mod_option_row(
            visual_frame,
            "Epoch Water",
            self.visual_mods["epoch_water"],
            "source: RetroCro",
            self.descriptions["epoch_water"],
        )
        self.create_mod_option_row(
            visual_frame,
            "Fog Pushback",
            self.visual_mods["fog_pushback"],
            "source: RetroCro",
            self.descriptions["fog_pushback"],
        )
        self.create_mod_option_row(
            visual_frame,
            "Pink Herbs",
            self.visual_mods["pink_herbs"],
            "by seacrabsam",
            self.descriptions["pink_herbs"],
        )

        self.create_mod_option_row(
            audio_frame,
            "NoErrorSounds",
            self.audio_mods["no_error_sounds"],
            "by Macumbafeh",
            self.descriptions["no_error_sounds"],
        )
        self.create_mod_option_row(
            audio_frame,
            "FishPing",
            self.audio_mods["fish_ping"],
            "by notsureawake",
            self.descriptions["fish_ping"],
        )
        self.create_mod_option_row(
            audio_frame,
            "Warlock Muted Demons",
            self.audio_mods["warlock_muted_demons"],
            "by spzilyk",
            self.descriptions["warlock_muted_demons"],
        )


    def build_credits_tab(self, parent):
        # Create a frame with a scrollbar
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side='right', fill='y')

        bg_color = self.root.cget('bg')
        text_area = tk.Text(
            frame,
            wrap='word',
            yscrollcommand=scrollbar.set,
            bg=bg_color,
            relief='flat',
            font=("Segoe UI", 9)
        )
        text_area.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=text_area.yview)

        # Configure Text Tags for formatting
        text_area.tag_configure(
            "header",
            font=("Segoe UI", 10, "bold"),
            spacing1=10,
            spacing3=5,
            foreground="#333333"
        )
        text_area.tag_configure("bold", font=("Segoe UI", 9, "bold"))

        # Helper function to create clickable links
        def insert_link(text, url):
            tag_name = f"link_{url}"
            text_area.tag_configure(tag_name, foreground="#005A9E", underline=True)
            text_area.tag_bind(tag_name, "<Button-1>", lambda e, u=url: webbrowser.open_new(u))
            text_area.tag_bind(tag_name, "<Enter>", lambda e: text_area.config(cursor="hand2"))
            text_area.tag_bind(tag_name, "<Leave>", lambda e: text_area.config(cursor="arrow"))
            text_area.insert("end", text, tag_name)

        text_area.insert(
            "end",
            "This modernization tool brings together work from several community projects and developers. "
            "Use the links below to view the original sources, documentation and releases.\n",
            ""
        )

        # Rendering & executable patching
        text_area.insert("end", "\nRendering & Client Patching\n", "header")
        text_area.insert("end", "• VanillaFixes: ", "bold")
        insert_link("Source Repository", "https://github.com/hannesmann/vanillafixes")

        text_area.insert("end", "\n• DXVK: ", "bold")
        insert_link("Source Repository", "https://github.com/doitsujin/dxvk")

        text_area.insert("end", "\n• Vanilla Tweaks: ", "bold")
        insert_link("Source Repository", "https://github.com/tubtubs/vanilla-tweaks")

        # Core engine & API plugins
        text_area.insert("end", "\n\nCore Engine & API Plugins\n", "header")
        text_area.insert("end", "• VanillaHelpers: ", "bold")
        insert_link("Source Repository", "https://github.com/isfir/VanillaHelpers")

        text_area.insert("end", "\n• PerfBoost: ", "bold")
        text_area.insert("end", "by avitasia | ")
        insert_link("Addon Source", "https://gitea.com/avitasia/PerfBoostSettings")

        text_area.insert("end", "\n• UnitXP_SP3: ", "bold")
        insert_link("Source Repository", "https://github.com/brues-code/UnitXP_SP3")
        text_area.insert("end", "  (DLL + UnitXP_SP3_Addon are distributed together in releases)")

        text_area.insert("end", "\n• SuperWoW: ", "bold")
        insert_link("Mod Source", "https://github.com/balakethelock/SuperWoW")
        text_area.insert("end", " | ")
        insert_link("SuperAPI Addon", "https://github.com/balakethelock/SuperAPI")

        text_area.insert("end", "\n• ClassicAPI: ", "bold")
        insert_link("Source Repository", "https://github.com/brues-code/ClassicAPI")

        text_area.insert("end", "\n• AuctionQueryThrottle: ", "bold")
        insert_link("Source Repository", "https://github.com/brues-code/AuctionQueryThrottle")

        text_area.insert("end", "\n• Nampower: ", "bold")
        insert_link("Mod Source", "https://github.com/brues-code/nampower")
        text_area.insert("end", " | ")
        insert_link("Addon Source", "https://github.com/brues-code/NampowerSettings")

        text_area.insert("end", "\n• No1600x1200: ", "bold")
        insert_link("Source / Backup", "https://github.com/RetroCro/TurtleWoW-Mods#no1600x1200")

        text_area.insert("end", "\n• VanillaMultiMonitorFix: ", "bold")
        insert_link("Source Repository", "https://github.com/Mates1500/VanillaMultiMonitorFix")

        text_area.insert("end", "\n• Interact: ", "bold")
        insert_link("Source Repository", "https://github.com/lookino/Interact")

        # Visual & audio mods
        text_area.insert("end", "\n\nVisual & Audio Mods\n", "header")

        text_area.insert("end", "• Bluemoon Patch: ", "bold")
        insert_link("via vanilla-tweaks", "https://github.com/tubtubs/vanilla-tweaks")

        text_area.insert("end", "\n• Darker Nights: ", "bold")
        insert_link("Project Reforged", "https://projectreforged.github.io/vanilla/downloads/turtle/")

        text_area.insert("end", "\n• Pretty Night Sky / Epoch Water / Fog Pushback: ", "bold")
        insert_link("RetroCro TurtleWoW Mods", "https://github.com/RetroCro/TurtleWoW-Mods")

        text_area.insert("end", "\n• Pink Herbs: ", "bold")
        insert_link("seacrabsam/patch-herb", "https://github.com/seacrabsam/patch-herb")

        text_area.insert("end", "\n• NoErrorSounds: ", "bold")
        insert_link("Macumbafeh/NoErrorSounds", "https://github.com/Macumbafeh/NoErrorSounds")

        text_area.insert("end", "\n• FishPing: ", "bold")
        insert_link("notsureawake/FishPing", "https://github.com/notsureawake/FishPing")

        text_area.insert("end", "\n• Warlock Muted Demons: ", "bold")
        insert_link("spzilyk/Warlock-Muted-Demons", "https://github.com/spzilyk/Warlock-Muted-Demons")

        text_area.insert("end", "\n• Automatically Clear WDB: ", "bold")
        insert_link("RetroCro guide", "https://github.com/RetroCro/TurtleWoW-Mods#automatically-clear-wdb-folder-every-time-you-launch-turtle-wow")

        # Other bundled enhancements
        text_area.insert("end", "\n\nOther Bundled Enhancements\n", "header")
        text_area.insert("end", "• Vanilla-Autologin: ", "bold")
        insert_link("Source Repository", "https://github.com/MarcelineVQ/turtle-autologin")
        text_area.insert(
            "end",
            "  (when AutoLogin + Nampower are selected, the tool creates or reuses "
            "WOW_ENCRYPTION_KEY automatically; existing keys are never replaced)"
        )

        text_area.insert("end", "\n• WowPresence: ", "bold")
        text_area.insert("end", "by Dusk-92 | ")
        insert_link("Source Repository", "https://github.com/Dusk-92/WowPresence")

        # WeirdUtils
        text_area.insert("end", "\n\nWeirdUtils Suite\n", "header")
        text_area.insert(
            "end",
            "The tool bundles or exposes these WeirdUtils modules: "
            "weirdperformance.dll, transmogfix.dll, bigcursor.dll, customassets.dll, "
            "logsessions.dll, minimapicons.dll, pngscreenshots.dll and worldmarkers.dll.\n"
        )
        text_area.insert(
            "end",
            "Some WeirdUtils components are distributed as pre-compiled binaries; see the project page "
            "for documentation and releases.\n\n"
        )
        text_area.insert("end", "• WeirdUtils Documentation & Releases: ", "bold")
        insert_link("Project Repository", "https://codeberg.org/MarcelineVQ/WeirdUtils")

        # This tool
        text_area.insert("end", "\n\nModernization Tool\n", "header")
        text_area.insert("end", "• WoW Modernization Tool: ", "bold")
        insert_link("Project Repository", "https://github.com/Dusk-92/Modernization-Tool")
        text_area.insert("end", "\n")

        # Lock text area to prevent editing
        text_area.config(state='disabled')


    def _inspect_wow_executable(self, wow_exe):
        """Validate the PE architecture without relying on a version-specific hash."""
        try:
            file_size = os.path.getsize(wow_exe)
            if file_size < 1024 * 1024:
                return False, "WoW.exe is unexpectedly small."

            with open(wow_exe, "rb") as handle:
                dos_header = handle.read(64)
                if len(dos_header) < 64 or dos_header[:2] != b"MZ":
                    return False, "WoW.exe is not a valid Windows executable."

                pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
                if pe_offset < 64 or pe_offset > file_size - 26:
                    return False, "WoW.exe has an invalid PE header."

                handle.seek(pe_offset)
                if handle.read(4) != b"PE\0\0":
                    return False, "WoW.exe has an invalid PE signature."

                coff = handle.read(20)
                if len(coff) != 20:
                    return False, "WoW.exe has a truncated PE header."

                machine = struct.unpack_from("<H", coff, 0)[0]
                optional_size = struct.unpack_from("<H", coff, 16)[0]
                if optional_size < 2:
                    return False, "WoW.exe has no valid optional PE header."

                optional_magic = struct.unpack("<H", handle.read(2))[0]

            # Vanilla 1.12/Turtle uses the 32-bit x86 PE format.
            if machine != 0x014C or optional_magic != 0x010B:
                return (
                    False,
                    "WoW.exe is not a 32-bit x86 client. Modernization Tool is "
                    "intended for Vanilla 1.12/Turtle-compatible clients only.",
                )

            return True, ""
        except (OSError, struct.error) as exc:
            return False, f"WoW.exe could not be inspected: {exc}"

    def _find_data_file_case_insensitive(self, data_dir, wanted):
        try:
            entries = {name.casefold(): name for name in os.listdir(data_dir)}
        except OSError:
            return None
        actual = entries.get(wanted.casefold())
        return os.path.join(data_dir, actual) if actual else None

    def validate_installation_dir(self, target_dir):
        """Validate a Vanilla/Turtle-compatible 32-bit client before patching."""
        if not target_dir:
            messagebox.showerror(
                "Directory Error",
                "Please select a Vanilla 1.12 installation directory.",
            )
            return False

        target_dir = os.path.abspath(target_dir)
        wow_exe = os.path.join(target_dir, "WoW.exe")
        data_dir = os.path.join(target_dir, "Data")
        interface_dir = os.path.join(target_dir, "Interface")

        if (
            not os.path.isfile(wow_exe)
            or not os.path.isdir(data_dir)
            or not os.path.isdir(interface_dir)
        ):
            messagebox.showerror(
                "Invalid Directory",
                "This does not look like a valid Vanilla 1.12 installation directory.\n\n"
                "Select the game directory that directly contains WoW.exe, Data and Interface.",
            )
            return False

        valid_pe, pe_reason = self._inspect_wow_executable(wow_exe)
        if not valid_pe:
            messagebox.showerror(
                "Unsupported WoW Client",
                pe_reason
                + "\n\nNo files were changed. Select a Vanilla 1.12/Turtle-compatible client.",
            )
            return False

        # These are core archives in the Vanilla/Turtle data layout. Requiring
        # them rejects most later-expansion/modern clients without tying the
        # tool to one exact Turtle WoW.exe hash.
        required_archives = ("base.MPQ", "dbc.MPQ", "interface.MPQ")
        missing = [
            name
            for name in required_archives
            if self._find_data_file_case_insensitive(data_dir, name) is None
        ]
        if missing:
            messagebox.showerror(
                "Unsupported WoW Client",
                "The selected client does not have the expected Vanilla/Turtle data layout.\n\n"
                "Missing core archive(s): "
                + ", ".join(missing)
                + "\n\nNo files were changed.",
            )
            return False

        return True

    def validate_limits(self):
        if self.safety_override.get():
            return True 
            
        try:
            if self.vt_farclip.get() > 1500:
                messagebox.showerror("Limit Exceeded", "Render distance (Farclip) exceeds the safe limit of 1500.\n\nPlease lower it, or check 'Disable Safety Limits' to bypass.")
                return False
            if self.vt_frill.get() > 300:
                messagebox.showerror("Limit Exceeded", "Ground clutter (Frilldistance) exceeds the safe limit of 300.\n\nPlease lower it, or check 'Disable Safety Limits' to bypass.")
                return False
            if self.vt_nameplate.get() > 41:
                messagebox.showerror("Limit Exceeded", "Nameplate range exceeds the safe limit of 41.\n\nPlease lower it, or check 'Disable Safety Limits' to bypass.")
                return False
            if self.vt_maxcam.get() > 100:
                messagebox.showerror("Limit Exceeded", "Camera distance exceeds the safe limit of 100.\n\nPlease lower it, or check 'Disable Safety Limits' to bypass.")
                return False
            if self.vt_soundchan.get() > 64:
                messagebox.showerror("Limit Exceeded", "Sound Channels exceed the safe limit of 64.\n\nPlease lower it, or check 'Disable Safety Limits' to bypass.")
                return False
            if self.vt_fov.get() > 2.2689: 
                messagebox.showerror("Limit Exceeded", "Field of View exceeds the safe limit of 130 degrees (2.2689 radians).\n\nPlease lower it, or check 'Disable Safety Limits' to bypass.")
                return False
        except tk.TclError:
            messagebox.showerror("Input Error", "Please ensure all Tweak fields contain valid numbers.")
            return False
            
        return True

    def clean_unselected_files(self, target):
        """Remove explicitly unselected tool-managed files without hiding failures."""

        def remove_managed_file(path, label):
            if not os.path.lexists(path):
                return
            try:
                os.remove(path)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not remove {label}. Close WoW and any program using the file, then try again."
                ) from exc

        def remove_managed_tree(path, label):
            if not os.path.lexists(path):
                return
            try:
                shutil.rmtree(path)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not remove {label}. Close WoW and any program using the folder, then try again."
                ) from exc

        # 1. Clean AutoLogin files if unselected.
        if not self.install_autologin.get():
            glue_dir = os.path.join(target, "Data", "Interface", "GlueXML")
            for file_name in ["AutoLogin.lua", "AutoLogin.xml", "GlueXML.toc"]:
                remove_managed_file(
                    os.path.join(glue_dir, file_name),
                    f"managed AutoLogin file {file_name}",
                )
            if os.path.isdir(glue_dir):
                try:
                    if not os.listdir(glue_dir):
                        os.rmdir(glue_dir)
                except OSError:
                    # Leaving an empty directory behind is harmless; unlike a
                    # stale DLL/AddOn it cannot change the running client.
                    pass

        # 2. Clean unselected Core Plugins and their dependent AddOns.
        for dll_name, var in self.core_plugins.items():
            if not var.get():
                remove_managed_file(
                    os.path.join(target, dll_name),
                    f"managed plugin {dll_name}",
                )

                addon_folder = self.addon_dependencies.get(dll_name)
                if addon_folder:
                    remove_managed_tree(
                        os.path.join(target, "Interface", "AddOns", addon_folder),
                        f"managed addon {addon_folder}",
                    )

        # 3. Clean unselected Optional plugins.
        for dll_name, var in self.optional_plugins.items():
            if not var.get():
                if dll_name == "WowPresence.dll":
                    # Only undo a WowPresence installation that this tool
                    # actually owns. A standalone/manual WowPresence install
                    # must survive an Apply with this option unchecked.
                    if remote_packages.managed_mod_has_manifest(
                        target,
                        remote_packages.WOWPRESENCE_MANAGED_ID,
                    ):
                        preexisting_entry = remote_packages.managed_mod_manifest_value(
                            target,
                            remote_packages.WOWPRESENCE_MANAGED_ID,
                            "dlls_entry_preexisting",
                            None,
                        )
                        if not isinstance(preexisting_entry, bool):
                            # Conservative migration for early test manifests:
                            # a saved DLL backup means WowPresence predated the
                            # tool, so preserve its dlls.txt entry.
                            preexisting_entry = remote_packages._managed_backup_exists(
                                target,
                                remote_packages.WOWPRESENCE_MANAGED_ID,
                                "WowPresence.dll",
                            )

                        if not preexisting_entry:
                            self._remove_dlls_entry(target, "WowPresence.dll")

                        # This restores any backed-up manual binaries, or
                        # removes only the copies installed by the tool.
                        remote_packages.remove_managed_mod(
                            target,
                            remote_packages.WOWPRESENCE_MANAGED_ID,
                        )
                    # Keep .modernization_tool\WowPresence user configuration.
                else:
                    remove_managed_file(
                        os.path.join(target, dll_name),
                        f"managed plugin {dll_name}",
                    )


    @staticmethod
    def _broadcast_environment_change():
        """Notify Windows shells that persistent user environment values changed."""
        if os.name != "nt":
            return
        try:
            import ctypes

            result = ctypes.c_ulong()
            ctypes.windll.user32.SendMessageTimeoutW(
                0xFFFF,       # HWND_BROADCAST
                0x001A,       # WM_SETTINGCHANGE
                0,
                "Environment",
                0x0002,       # SMTO_ABORTIFHUNG
                5000,
                ctypes.byref(result),
            )
        except (AttributeError, OSError):
            # The registry value is already persistent. A failed broadcast only
            # means some already-running shells may not see it until restarted.
            pass

    def configure_autologin_encryption(self):
        """Create the Nampower AutoLogin entropy key once, never rotate it."""
        autologin_enabled = bool(self.install_autologin.get())
        nampower_var = self.core_plugins.get("nampower.dll")
        nampower_enabled = bool(nampower_var is not None and nampower_var.get())

        if not (autologin_enabled and nampower_enabled):
            return "not-needed"

        variable_name = "WOW_ENCRYPTION_KEY"

        # Respect any value already inherited by this process. It may come from
        # a machine-level policy or another legitimate user configuration.
        inherited = os.environ.get(variable_name)
        if inherited:
            return "existing"

        if winreg is None:
            raise RuntimeError(
                "AutoLogin password encryption could not be configured because "
                "the Windows registry API is unavailable."
            )

        # Prefer an existing per-user registry value even if this process was
        # started before Windows propagated it into the environment.
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_READ,
            ) as key:
                existing, _value_type = winreg.QueryValueEx(key, variable_name)
            if isinstance(existing, str) and existing:
                os.environ[variable_name] = existing
                self._broadcast_environment_change()
                return "existing"
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(
                "AutoLogin password encryption could not read the current "
                "Windows user environment settings."
            ) from exc

        # 256 bits of random entropy encoded as plain hex. The key is persisted
        # only in HKCU\Environment; it is deliberately never written to the WoW
        # folder, settings.json, logs, dialogs, or console output.
        generated = secrets.token_hex(32)
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(
                    key,
                    variable_name,
                    0,
                    winreg.REG_SZ,
                    generated,
                )
        except OSError as exc:
            raise RuntimeError(
                "AutoLogin password encryption could not create the Windows "
                "user encryption key."
            ) from exc

        # Make the current process consistent immediately and notify Explorer
        # so shortcuts launched after Apply inherit the new variable without a
        # sign-out/reboot on normal Windows configurations.
        os.environ[variable_name] = generated
        self._broadcast_environment_change()
        return "created"

    def configure_script_memory(self, target):
        """Optionally set AddOn Script Memory to 0 (unlimited) in WTF/Config.wtf."""
        if not self.vt_script_memory.get():
            return

        wtf_dir = os.path.join(target, "WTF")
        config_path = os.path.join(wtf_dir, "Config.wtf")
        original_mode = None
        restore_readonly = False

        try:
            os.makedirs(wtf_dir, exist_ok=True)

            if os.path.exists(config_path):
                original_mode = os.stat(config_path).st_mode
                if not (original_mode & stat.S_IWRITE):
                    os.chmod(config_path, original_mode | stat.S_IWRITE)
                    restore_readonly = True

            existing = ""
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                    existing = f.read()

            setting = 'SET scriptMemory "0"'
            pattern = re.compile(
                r'^\s*SET\s+scriptMemory\s+"[^"]*"\s*$',
                re.IGNORECASE | re.MULTILINE
            )

            if pattern.search(existing):
                updated = pattern.sub(setting, existing)
            else:
                if existing and not existing.endswith(("\n", "\r")):
                    existing += "\n"
                updated = existing + setting + "\n"

            with open(config_path, "w", encoding="utf-8", newline="") as f:
                f.write(updated)

        except PermissionError as exc:
            raise RuntimeError(
                "Windows denied access to WTF\\Config.wtf. Close WoW and any "
                "program using the file. If your WoW folder is protected, run "
                "the Modernization Tool as administrator and try again."
            ) from exc
        finally:
            if restore_readonly and original_mode is not None and os.path.exists(config_path):
                try:
                    os.chmod(config_path, original_mode)
                except OSError:
                    pass


    def _wdb_marker_path(self, target_dir):
        return os.path.join(
            target_dir,
            ".modernization_tool",
            "wdb_blocker.json",
        )

    def _previous_settings_used_wdb_blocker(self, target_dir):
        """Use the last successful settings file as legacy ownership evidence."""
        settings_path = self._settings_path(target_dir)
        if not os.path.isfile(settings_path):
            return False
        try:
            with open(settings_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            tweaks = saved.get("vanilla_tweaks", {})
            return isinstance(tweaks, dict) and tweaks.get("clear_wdb") is True
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return False

    def _wdb_blocker_owned_by_tool(self, target_dir):
        marker_path = self._wdb_marker_path(target_dir)
        if os.path.isfile(marker_path):
            try:
                with open(marker_path, "r", encoding="utf-8") as handle:
                    marker = json.load(handle)
                if (
                    isinstance(marker, dict)
                    and marker.get("target") == "WDB"
                    and marker.get("type") == "empty_file_blocker"
                ):
                    return True
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass

        return self._previous_settings_used_wdb_blocker(target_dir)

    def _write_wdb_marker(self, target_dir):
        marker_path = self._wdb_marker_path(target_dir)
        os.makedirs(os.path.dirname(marker_path), exist_ok=True)
        temp_path = marker_path + ".new"
        payload = {
            "schema": 1,
            "target": "WDB",
            "type": "empty_file_blocker",
            "expected_size": 0,
        }
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temp_path, marker_path)

    def configure_wdb_cache(self, target):
        """Apply/remove the RetroCro WDB blocker without deleting foreign files."""
        wdb_path = os.path.join(target, "WDB")
        marker_path = self._wdb_marker_path(target)

        if self.vt_clear_wdb.get():
            if os.path.islink(wdb_path):
                raise RuntimeError(
                    "WDB is a symbolic link. Remove it manually before enabling "
                    "Automatically Clear WDB."
                )

            if os.path.isdir(wdb_path):
                # Clearing the real WDB cache is the explicit purpose of this
                # option. After removal we create our own empty blocker.
                shutil.rmtree(wdb_path)

            elif os.path.exists(wdb_path) and not os.path.isfile(wdb_path):
                raise RuntimeError(
                    "The existing WDB path is not a normal file or directory."
                )

            elif os.path.isfile(wdb_path):
                # A zero-byte WDB is already a blocker. Because the user has
                # explicitly enabled this option, it is safe to adopt that
                # blocker into tool ownership. Never adopt a non-empty file.
                try:
                    size = os.path.getsize(wdb_path)
                except OSError as exc:
                    raise RuntimeError(
                        f"Could not inspect the existing WDB file: {exc}"
                    ) from exc

                if size != 0:
                    raise RuntimeError(
                        "A non-empty file named WDB already exists in the game "
                        "folder. Modernization Tool will not overwrite or claim "
                        "ownership of it. Rename/remove that file manually before "
                        "enabling Automatically Clear WDB."
                    )

            if not os.path.exists(wdb_path):
                with open(wdb_path, "wb"):
                    pass

            # At this point WDB is guaranteed to be the empty blocker selected
            # by the user. Record ownership atomically for later removal.
            try:
                self._write_wdb_marker(target)
            except OSError:
                # settings.json, saved after a successful Apply, also provides
                # legacy ownership evidence on the next run.
                pass
            return

        # Disabled: remove only a blocker that this tool can identify as its
        # own, and only if it is still an empty regular file. A replaced or
        # foreign WDB file is never deleted.
        owned = self._wdb_blocker_owned_by_tool(target)

        if os.path.isfile(wdb_path) and owned:
            try:
                size = os.path.getsize(wdb_path)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not inspect the WDB blocker before removal: {exc}"
                ) from exc

            if size == 0:
                try:
                    os.chmod(
                        wdb_path,
                        os.stat(wdb_path).st_mode | stat.S_IWRITE,
                    )
                except OSError:
                    pass
                os.remove(wdb_path)
            else:
                messagebox.showwarning(
                    "WDB file preserved",
                    "Modernization Tool previously created a WDB blocker here, "
                    "but the current WDB file is no longer empty. It may have "
                    "been replaced by another program, so it was left untouched.",
                )

        elif os.path.isfile(wdb_path) and not owned:
            messagebox.showwarning(
                "WDB file preserved",
                "A regular file named WDB already exists, but Modernization Tool "
                "cannot verify that it created it. The file was left untouched.",
            )

        # A real WDB directory is always left alone when the option is disabled.
        # Remove stale ownership metadata only after the blocker is gone or no
        # longer ours.
        if os.path.isfile(marker_path):
            try:
                os.remove(marker_path)
            except OSError:
                pass

    def configure_visual_audio(self, target):
        progress = getattr(self, "_report_download_progress", None)
        close_progress = getattr(self, "_close_download_progress", None)
        warnings = []

        visual_defs = [
            (
                "darker_nights",
                "visual_darker_nights",
                "Darker Nights",
                remote_packages.install_darker_nights,
            ),
            (
                "pretty_night_sky",
                "visual_pretty_night_sky",
                "Pretty Night Sky",
                remote_packages.install_pretty_night_sky,
            ),
            (
                "epoch_water",
                "visual_epoch_water",
                "Epoch Water",
                remote_packages.install_epoch_water,
            ),
            (
                "fog_pushback",
                "visual_fog_pushback",
                "Fog Pushback",
                remote_packages.install_fog_pushback,
            ),
            (
                "pink_herbs",
                "visual_pink_herbs",
                "Pink Herbs",
                remote_packages.install_pink_herbs,
            ),
        ]
        audio_defs = [
            (
                "no_error_sounds",
                "audio_no_error_sounds",
                "NoErrorSounds",
                remote_packages.install_no_error_sounds,
                os.path.join("Audio", "NoErrorSounds", "Sound"),
                "Sound",
            ),
            (
                "fish_ping",
                "audio_fish_ping",
                "FishPing",
                remote_packages.install_fish_ping,
                os.path.join("Audio", "FishPing", "Sound"),
                "Sound",
            ),
            (
                "warlock_muted_demons",
                "audio_warlock_muted_demons",
                "Warlock Muted Demons",
                remote_packages.install_warlock_muted_demons,
                os.path.join("Audio", "WarlockMutedDemons", "Data"),
                "Data",
            ),
        ]

        # MPQ fallbacks were intentionally removed. Clean caches created by
        # earlier test builds so they cannot be reused later.
        for _, managed_id, _, _ in visual_defs:
            remote_packages.remove_package_cache(target, managed_id)

        try:
            # Visual installers own their current-version checks.
            # Already valid MPQs are reused without a download.
            for key, managed_id, display_name, installer in visual_defs:
                if self.visual_mods[key].get():
                    try:
                        installer(target, progress=progress)
                    except remote_packages.RemoteSourceUnavailable as exc:
                        if remote_packages.managed_mpq_is_usable(target, managed_id):
                            warnings.append(
                                f"{display_name}: update source unavailable; existing installed copy kept."
                            )
                        else:
                            raise RuntimeError(
                                f"{display_name} source is unavailable and no valid installed copy can be kept:\n{exc}"
                            ) from exc
                    except Exception as exc:
                        raise RuntimeError(
                            f"{display_name} installation failed locally:\n{exc}"
                        ) from exc
                else:
                    remote_packages.remove_managed_mod(target, managed_id)

            fallback_root = os.path.join(get_base_path(), "Payload", "Fallback")
            for (
                key,
                managed_id,
                display_name,
                installer,
                fallback_rel,
                destination_prefix,
            ) in audio_defs:
                if self.audio_mods[key].get():
                    try:
                        installer(target, progress=progress)
                    except Exception as exc:
                        if remote_packages.managed_mod_is_installed(target, managed_id):
                            warnings.append(
                                f"{display_name}: online source unavailable; existing installed copy kept."
                            )
                            continue

                        bundled = os.path.join(fallback_root, fallback_rel)
                        if not os.path.isdir(bundled):
                            raise RuntimeError(
                                f"{display_name} installation failed and its bundled backup is missing:\n{exc}"
                            ) from exc

                        remote_packages.install_bundled_tree(
                            target,
                            managed_id,
                            bundled,
                            destination_prefix,
                        )
                        warnings.append(
                            f"{display_name}: online source unavailable; bundled backup installed."
                        )
                else:
                    remote_packages.remove_managed_mod(target, managed_id)
        finally:
            if callable(close_progress):
                close_progress()

        if warnings:
            messagebox.showwarning(
                "Some online sources were unavailable",
                "\n\n".join(warnings),
            )


    def _dep_marker_path(self, target_dir):
        return os.path.join(
            target_dir,
            ".modernization_tool",
            "dep_override.json",
        )

    def _previous_settings_used_dep_override(self, target_dir):
        """Use the last successful settings file as migration/ownership evidence."""
        settings_path = self._settings_path(target_dir)
        if not os.path.isfile(settings_path):
            return False
        try:
            with open(settings_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            tweaks = saved.get("vanilla_tweaks", {})
            return isinstance(tweaks, dict) and tweaks.get("dep_fix") is True
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return False

    def _dep_override_owned_by_tool(self, target_dir):
        return (
            os.path.isfile(self._dep_marker_path(target_dir))
            or self._previous_settings_used_dep_override(target_dir)
        )

    def _run_elevated_powershell(self, target_dir, script_text, action_name):
        """Run one small PowerShell script elevated and verify its exit code."""
        support_dir = os.path.join(target_dir, ".modernization_tool")
        os.makedirs(support_dir, exist_ok=True)
        script_path = os.path.join(support_dir, "process_mitigation.ps1")

        with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("$ErrorActionPreference = 'Stop'\n")
            handle.write(script_text.rstrip() + "\n")
            handle.write("exit 0\n")

        escaped_script = script_path.replace("'", "''")
        launcher = (
            "$ErrorActionPreference='Stop'; "
            f"$scriptPath = '{escaped_script}'; "
            "$argumentLine = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"' "
            "+ $scriptPath + '\"'; "
            "try { "
            "$p = Start-Process -FilePath 'powershell.exe' -Verb RunAs "
            "-Wait -PassThru -ArgumentList $argumentLine; "
            "exit $p.ExitCode "
            "} catch { Write-Error $_; exit 1 }"
        )

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    launcher,
                ],
                creationflags=0x08000000,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"{action_name} could not run because Windows PowerShell was not found."
            ) from exc
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            if len(details) > 800:
                details = details[-800:]
            suffix = f"\n\nDetails: {details}" if details else ""
            raise RuntimeError(
                f"{action_name} was not completed. The Administrator/UAC prompt may "
                f"have been declined, or Windows rejected the mitigation change.{suffix}"
            )

    def apply_process_mitigations(self, target_dir):
        """Apply or restore the per-app DEP override with verified UAC completion."""
        marker_path = self._dep_marker_path(target_dir)

        if self.vt_dep_fix.get():
            self._run_elevated_powershell(
                target_dir,
                "Set-ProcessMitigation -Name 'WoW_Modernized.exe' "
                "-Disable DEP, EmulateAtlThunks",
                "Disabling DEP for WoW_Modernized.exe",
            )

            # Keep explicit ownership evidence so disabling this option later
            # restores only a setting that Modernization Tool applied.
            try:
                os.makedirs(os.path.dirname(marker_path), exist_ok=True)
                temp_marker = marker_path + ".new"
                with open(temp_marker, "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "target": "WoW_Modernized.exe",
                            "disabled": ["DEP", "EmulateAtlThunks"],
                        },
                        handle,
                        indent=2,
                    )
                os.replace(temp_marker, marker_path)
            except OSError:
                # settings.json is also ownership evidence after a successful
                # Apply, so a marker write failure must not invalidate DEP.
                pass
            return

        if not self._dep_override_owned_by_tool(target_dir):
            return

        # Microsoft documents -Remove together with -Disable for restoring an
        # app-specific mitigation override back to the system default.
        self._run_elevated_powershell(
            target_dir,
            "Set-ProcessMitigation -Name 'WoW_Modernized.exe' "
            "-Remove -Disable DEP, EmulateAtlThunks",
            "Restoring the system DEP defaults for WoW_Modernized.exe",
        )

        try:
            os.remove(marker_path)
        except OSError:
            pass

    def _set_install_busy(self, busy):
        self._install_in_progress = bool(busy)
        button = getattr(self, "apply_button", None)
        if button is not None:
            try:
                button.configure(
                    state="disabled" if busy else "normal",
                    text="Applying Setup..." if busy else "Apply Setup & Tweaks",
                )
            except tk.TclError:
                pass
        try:
            self.root.configure(cursor="wait" if busy else "")
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def run_installation(self):
        # Progress callbacks intentionally process Tk events. This explicit
        # guard prevents a second Apply event from entering the installer while
        # the first one is still running.
        if self._install_in_progress:
            return

        self._set_install_busy(True)
        try:
            target_dir = self.wow_dir.get().strip()

            # 1. Validate Directory / client architecture.
            if not self.validate_installation_dir(target_dir):
                return

            # 2. Validate Bounds.
            if not self.validate_limits():
                return

            # 3. Validate plugin combinations independently of UI callbacks.
            if not self.validate_plugin_conflicts():
                return

            try:
                self.clean_unselected_files(target_dir)
                self.copy_base_files(target_dir)
                self.configure_dxvk(target_dir)
                self.configure_plugins(target_dir)
                self.configure_autologin_encryption()
                self.configure_visual_audio(target_dir)
                self.run_vanilla_tweaks(target_dir)
                self.configure_script_memory(target_dir)
                self.configure_wdb_cache(target_dir)
                self.apply_process_mitigations(target_dir)

                # Generate the seamless launcher shortcut.
                self.create_launcher_shortcut(target_dir)
                self.cleanup_legacy_outputs(target_dir)

                settings_warning = ""
                try:
                    self.save_settings(target_dir)
                except OSError as exc:
                    settings_warning = (
                        "\n\nWarning: your choices could not be saved for the next run. "
                        f"Details: {exc}"
                    )

                messagebox.showinfo(
                    "Success",
                    "Installation and patching complete!\n\n"
                    "'Play Modernized WoW' shortcuts were created in:\n"
                    "• your WoW game folder\n"
                    "• your Windows desktop\n\n"
                    "Use either shortcut to launch the modernized game."
                    + settings_warning,
                )
            except PermissionError as exc:
                messagebox.showerror(
                    "Permission Error",
                    "Windows denied access to a file or folder in the selected WoW directory.\n\n"
                    "Close WoW and any program using the files. If the folder is protected, "
                    "run the Modernization Tool as administrator and try again.\n\n"
                    f"Details: {exc}",
                )
            except Exception as exc:
                messagebox.showerror("Installation Error", str(exc))
        finally:
            # Never leave the UI locked after validation errors, network
            # failures, cancelled UAC prompts or installation exceptions.
            close_progress = getattr(self, "_close_download_progress", None)
            if callable(close_progress):
                close_progress()
            self._set_install_busy(False)

    def cleanup_legacy_outputs(self, target_dir):
        """Remove only known leftovers from older Modernization Tool builds."""
        modernized = os.path.join(target_dir, "WoW_Modernized.exe")
        if not os.path.exists(modernized):
            return

        # These names were generated by the old WoW_Tweaked.exe workflow and
        # are no longer used after switching to WoW_Modernized.exe.
        legacy_names = (
            "WoW_Tweaked.exe",
            "WoW_Tweaked.dxvk-cache",
            "WoW_Tweaked_d3d9.log",
        )
        for filename in legacy_names:
            path = os.path.join(target_dir, filename)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    # Cleanup is best-effort and must not turn a successful
                    # installation into an error because a stale log is locked.
                    pass

        # New shortcuts keep the icon in the tool's own support directory.
        # Remove the old root copy only after the replacement exists.
        managed_icon = os.path.join(
            target_dir,
            ".modernization_tool",
            "PurpleWowLogo.ico",
        )
        root_icon = os.path.join(target_dir, "PurpleWowLogo.ico")
        if os.path.isfile(managed_icon) and os.path.isfile(root_icon):
            try:
                os.remove(root_icon)
            except OSError:
                pass

    def create_launcher_shortcut(self, target_dir):
        """Create matching game-folder and Desktop launchers transactionally."""
        shortcut_path = os.path.join(target_dir, "Play Modernized WoW.lnk")
        staged_shortcut = shortcut_path + ".modernization-new.lnk"
        vanilla_fixes_exe = os.path.join(target_dir, "VanillaFixes.exe")
        modernized_exe = os.path.join(target_dir, "WoW_Modernized.exe")

        # Keep the launcher path unchanged. When enabled, WowPresence.dll
        # starts WowPresence.exe from its worker thread after WoW is running.
        launcher_exe = vanilla_fixes_exe
        launcher_arguments = "WoW_Modernized.exe"
        launcher_description = "Launch Vanilla WoW with VanillaFixes and Tweaks"

        if not os.path.isfile(vanilla_fixes_exe):
            raise RuntimeError(
                "VanillaFixes.exe is missing, so the launcher shortcuts cannot be created."
            )
        if not os.path.isfile(modernized_exe):
            raise RuntimeError(
                "WoW_Modernized.exe is missing, so the launcher shortcuts cannot be created."
            )

        support_dir = os.path.join(target_dir, ".modernization_tool")
        os.makedirs(support_dir, exist_ok=True)

        source_icon = os.path.join(get_base_path(), "PurpleWowLogo.ico")
        target_icon = os.path.join(support_dir, "PurpleWowLogo.ico")
        icon_vbs_line = ""

        if os.path.isfile(source_icon):
            try:
                remote_packages._atomic_replace_file(source_icon, target_icon)
                escaped_icon = (target_icon + ", 0").replace('"', '""')
                icon_vbs_line = f'oLink.IconLocation = "{escaped_icon}"'
            except Exception:
                # A custom icon is cosmetic; shortcut creation may continue.
                icon_vbs_line = ""

        def vbs_escape(value):
            return str(value).replace('"', '""')

        # WScript.Shell resolves the real Windows Desktop path, including
        # localized/OneDrive-redirected desktops. Echo it back so Python can
        # install the same verified shortcut there.
        vbs_script = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{vbs_escape(staged_shortcut)}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{vbs_escape(launcher_exe)}"
oLink.Arguments = "{vbs_escape(launcher_arguments)}"
oLink.WorkingDirectory = "{vbs_escape(target_dir)}"
oLink.Description = "{vbs_escape(launcher_description)}"
{icon_vbs_line}
oLink.Save
WScript.Echo oWS.SpecialFolders("Desktop")
"""
        vbs_path = os.path.join(support_dir, "create_shortcut.vbs")

        if os.path.exists(staged_shortcut):
            try:
                os.remove(staged_shortcut)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not prepare the launcher shortcut update: {exc}"
                ) from exc

        try:
            with open(vbs_path, "w", encoding="utf-8", newline="\r\n") as handle:
                handle.write(vbs_script)

            try:
                result = subprocess.run(
                    ["cscript", "//nologo", vbs_path],
                    creationflags=0x08000000,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Windows Script Host (cscript.exe) was not found, so the "
                    "launcher shortcuts could not be created."
                ) from exc

            if result.returncode != 0:
                details = (result.stderr or result.stdout or "").strip()
                if len(details) > 800:
                    details = details[-800:]
                suffix = f"\n\nDetails: {details}" if details else ""
                raise RuntimeError(
                    "Windows Script Host failed to create the launcher shortcut."
                    + suffix
                )

            if (
                not os.path.isfile(staged_shortcut)
                or os.path.getsize(staged_shortcut) <= 0
            ):
                raise RuntimeError(
                    "Windows reported successful shortcut creation, but the new "
                    "Play Modernized WoW shortcut was not produced."
                )

            desktop_lines = [
                line.strip()
                for line in (result.stdout or "").splitlines()
                if line.strip()
            ]
            desktop_dir = desktop_lines[-1] if desktop_lines else ""
            if not desktop_dir or not os.path.isdir(desktop_dir):
                raise RuntimeError(
                    "Windows could not resolve your Desktop folder, so the "
                    "Play Modernized WoW Desktop shortcut could not be created."
                )

            desktop_shortcut = os.path.join(
                desktop_dir,
                "Play Modernized WoW.lnk",
            )

            # Commit both launchers as one transaction. If either destination
            # cannot be updated, the previous shortcuts are restored.
            remote_packages._transactional_replace_bundle(
                [
                    ("file", staged_shortcut, shortcut_path),
                    ("file", staged_shortcut, desktop_shortcut),
                ],
                label="Play Modernized WoW shortcuts",
            )

        finally:
            for temp_path in (vbs_path, staged_shortcut):
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

    def copy_base_files(self, target):
        payload_dir = os.path.join(get_base_path(), "Payload")
        if not os.path.exists(payload_dir): return 
        
        if self.install_autologin.get() and os.path.exists(os.path.join(payload_dir, "Data")):
            shutil.copytree(os.path.join(payload_dir, "Data"), os.path.join(target, "Data"), dirs_exist_ok=True)
        
        if os.path.exists(os.path.join(payload_dir, "Interface")):
            shutil.copytree(os.path.join(payload_dir, "Interface"), os.path.join(target, "Interface"), dirs_exist_ok=True)
            
        # Removed SuperWoWhook.dll from this list!
        for file in ["VanillaFixes.exe", "VfPatcher.dll"]:
            source_file = os.path.join(payload_dir, file)
            if os.path.exists(source_file): shutil.copy2(source_file, target)


    def _previous_settings_used_dxvk(self, target):
        """Use the previous saved selection as legacy ownership proof."""
        settings_path = self._settings_path(target)
        if not os.path.isfile(settings_path):
            return False
        try:
            with open(settings_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return False
        return (
            isinstance(saved, dict)
            and saved.get("rendering_mode") == "dxvk"
        )

    def _external_renderer_backup_dir(self, target):
        return os.path.join(
            target,
            ".modernization_tool",
            "backups",
            "external_renderer",
        )

    def _park_external_renderer_file(self, target, filename):
        """Move an unowned D3D9 wrapper out of the game root without deleting it."""
        source = os.path.join(target, filename)
        if not os.path.lexists(source):
            return

        if os.path.islink(source) or not os.path.isfile(source):
            raise RuntimeError(
                f"Cannot safely disable the existing {filename}: it is not a regular file."
            )

        backup_dir = self._external_renderer_backup_dir(target)
        backup = os.path.join(backup_dir, filename)
        os.makedirs(backup_dir, exist_ok=True)

        if os.path.isfile(backup):
            try:
                same_file = (
                    self._file_sha256(source) == self._file_sha256(backup)
                )
            except OSError as exc:
                raise RuntimeError(
                    f"Could not compare the existing {filename} with its saved backup."
                ) from exc

            if not same_file:
                raise RuntimeError(
                    f"Cannot safely disable {filename}: a different saved renderer backup already exists at "
                    f"{backup}. Move or rename that backup manually, then try again."
                )

            try:
                os.remove(source)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not move {filename} out of the game root. Close WoW and any program using it, then try again."
                ) from exc
            return

        try:
            os.replace(source, backup)
        except OSError as exc:
            raise RuntimeError(
                f"Could not back up {filename} before disabling the external renderer. "
                "Close WoW and any program using it, then try again."
            ) from exc

    def configure_dxvk(self, target):
        """Apply the selected renderer while preserving pre-existing wrapper files."""
        payload_dir = os.path.join(get_base_path(), "Payload")
        d3d9_src = os.path.join(payload_dir, "DXVK_Standard", "d3d9.dll")
        conf_src = os.path.join(payload_dir, "dxvk.conf")
        d3d9_target = os.path.join(target, "d3d9.dll")
        conf_target = os.path.join(target, "dxvk.conf")
        managed_id = "renderer_dxvk"

        managed_files = remote_packages._load_managed_manifest(target, managed_id)

        if self.rendering_mode.get() == "dxvk":
            missing = [
                path for path in (d3d9_src, conf_src)
                if not os.path.isfile(path)
            ]
            if missing:
                raise FileNotFoundError(
                    "Bundled DXVK files are incomplete: "
                    + ", ".join(os.path.basename(path) for path in missing)
                )

            if not managed_files and self._previous_settings_used_dxvk(target):
                for path in (conf_target, d3d9_target):
                    if os.path.lexists(path):
                        try:
                            os.remove(path)
                        except OSError as exc:
                            raise RuntimeError(
                                f"Could not migrate the previous managed DXVK file {os.path.basename(path)}. "
                                "Close WoW and any program using it, then try again."
                            ) from exc

            remote_packages._install_managed_files_transactional(
                target,
                managed_id,
                [
                    (d3d9_src, "d3d9.dll"),
                    (conf_src, "dxvk.conf"),
                ],
                revision="1",
            )
            return

        if managed_files:
            remote_packages.remove_managed_mod(target, managed_id)
        elif self._previous_settings_used_dxvk(target):
            for path in (conf_target, d3d9_target):
                if os.path.lexists(path):
                    try:
                        os.remove(path)
                    except OSError as exc:
                        raise RuntimeError(
                            f"Could not remove the previous managed DXVK file {os.path.basename(path)}. "
                            "Close WoW and any program using it, then try again."
                        ) from exc

        for filename in ("d3d9.dll", "dxvk.conf"):
            self._park_external_renderer_file(target, filename)


    def _managed_dll_entries(self, target=None):
        """Return dlls.txt entries this tool is allowed to rewrite."""
        managed = {"dxvk"}
        managed.update(name.casefold() for name in self.core_plugins)

        for name, var in self.optional_plugins.items():
            if name.casefold() == "wowpresence.dll" and target is not None:
                selected = bool(var.get())
                owned = remote_packages.managed_mod_has_manifest(
                    target,
                    remote_packages.WOWPRESENCE_MANAGED_ID,
                )
                if not selected and not owned:
                    # A standalone WowPresence.dll line is user-owned.
                    continue
            managed.add(name.casefold())

        managed.update(
            name.casefold()
            for name in (
                "ClassicAPI.dll",
                "AuctionQueryThrottle.dll",
                "VanillaMultiMonitorFix.dll",
                "Interact.dll",
                # Legacy test-branch name. Owning it here removes the stale
                # entry from dlls.txt when migrating to WowPresence.dll.
                "DiscordPresence.dll",
            )
        )
        return managed

    @staticmethod
    def _remove_dlls_entry(target, entry):
        """Remove one exact DLL entry while preserving all unrelated lines."""
        dlls_path = os.path.join(target, "dlls.txt")
        if not os.path.isfile(dlls_path):
            return
        wanted = str(entry).strip().casefold()
        try:
            with open(dlls_path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.read().splitlines()
        except OSError as exc:
            raise RuntimeError(f"Could not read existing dlls.txt: {exc}") from exc

        kept = [
            line for line in lines
            if line.strip().casefold() != wanted
        ]
        staged = dlls_path + ".modernization-new"
        try:
            with open(staged, "w", encoding="utf-8", newline="\n") as handle:
                if kept:
                    handle.write("\n".join(kept) + "\n")
            os.replace(staged, dlls_path)
        except OSError as exc:
            try:
                if os.path.exists(staged):
                    os.remove(staged)
            except OSError:
                pass
            raise RuntimeError(f"Could not update existing dlls.txt: {exc}") from exc

    def _write_dlls_file(self, target, active_managed_lines):
        """Rewrite only tool-owned dlls.txt entries and preserve user entries."""
        dlls_path = os.path.join(target, "dlls.txt")
        managed_names = self._managed_dll_entries(target)
        preserved = []
        seen_preserved = set()

        if os.path.isfile(dlls_path):
            try:
                with open(dlls_path, "r", encoding="utf-8", errors="ignore") as handle:
                    existing_lines = handle.read().splitlines()
            except OSError as exc:
                raise RuntimeError(f"Could not read existing dlls.txt: {exc}") from exc

            for raw_line in existing_lines:
                stripped = raw_line.strip()
                if not stripped:
                    continue

                # Preserve comments exactly; they may document manual plugins.
                if stripped.startswith(("#", ";")):
                    preserved.append(raw_line.rstrip())
                    continue

                if stripped.casefold() in managed_names:
                    continue

                # Preserve unknown/manual entries once, case-insensitively.
                key = stripped.casefold()
                if key not in seen_preserved:
                    preserved.append(raw_line.rstrip())
                    seen_preserved.add(key)

        active = []
        seen_active = set()
        for line in active_managed_lines:
            stripped = str(line).strip()
            if not stripped:
                continue
            key = stripped.casefold()
            if key not in seen_active:
                active.append(stripped)
                seen_active.add(key)

        output_lines = list(active)
        if output_lines and preserved:
            output_lines.append("")
        output_lines.extend(preserved)

        staged = dlls_path + ".modernization-new"
        try:
            with open(staged, "w", encoding="utf-8", newline="\n") as handle:
                if output_lines:
                    handle.write("\n".join(output_lines) + "\n")
            os.replace(staged, dlls_path)
        except OSError as exc:
            raise RuntimeError(f"Could not update dlls.txt: {exc}") from exc
        finally:
            if os.path.exists(staged):
                try:
                    os.remove(staged)
                except OSError:
                    pass

    def configure_plugins(self, target):
        payload_base = os.path.join(get_base_path(), "Payload")
        payload_weirdu = os.path.join(payload_base, "WeirdUtils")
        
        dlls_text_lines = []
        if self.rendering_mode.get() == "dxvk":
            dlls_text_lines.append("dxvk")

        # Process Core Plugins
        for dll_name, var in self.core_plugins.items():
            if var.get():
                source_dll = os.path.join(payload_base, dll_name)
                if os.path.exists(source_dll): 
                    shutil.copy2(source_dll, target)
                dlls_text_lines.append(dll_name) 

        # Clean up corresponding addons if their core DLL was UNCHECKED
        for dll_name, addon_folder in self.addon_dependencies.items():
            if not self.core_plugins.get(dll_name, tk.BooleanVar(value=True)).get():
                addon_path = os.path.join(target, "Interface", "AddOns", addon_folder)
                if os.path.exists(addon_path):
                    shutil.rmtree(addon_path, ignore_errors=True)

        # Process Optional Plugins - installed to the game root.
        for dll_name, var in self.optional_plugins.items():
            if var.get():
                source_base = payload_base if dll_name == "no1600x1200.dll" else payload_weirdu
                source_dll = os.path.join(source_base, dll_name)
                if os.path.exists(source_dll):
                    shutil.copy2(source_dll, target)
                dlls_text_lines.append(dll_name)

        # Update only entries owned by this tool. Unknown/manual lines are kept.
        self._write_dlls_file(target, dlls_text_lines)

    def _file_sha256(self, path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _vanilla_tweaks_signature(self):
        """Return settings that change WoW_Modernized.exe patch output."""
        return {
            "fov": round(float(self.vt_fov.get()), 4),
            "farclip": int(self.vt_farclip.get()),
            "frill": int(self.vt_frill.get()),
            "nameplate": int(self.vt_nameplate.get()),
            "sound_channels": int(self.vt_soundchan.get()),
            "max_camera": int(self.vt_maxcam.get()),
            "quickloot": bool(self.vt_quickloot.get()),
            "background_sound": bool(self.vt_bg_sound.get()),
            "large_address_aware": bool(self.vt_laa.get()),
            "camera_fix": bool(self.vt_cam_fix.get()),
            "crossfaction_res": bool(self.vt_crossfaction_res.get()),
            "custom_glues": bool(self.vt_custom_glues.get()),
            "bluemoon": bool(self.vt_bluemoon.get()),
        }

    def run_vanilla_tweaks(self, target, tweaks_exe=None, modern_cli=False):
        """Patch a copy of WoW.exe while preserving the original executable."""
        wow_exe = os.path.join(target, "WoW.exe")
        if tweaks_exe is None:
            tweaks_exe = os.path.join(get_base_path(), "vanilla-tweaks.exe")

        if not os.path.exists(tweaks_exe):
            raise FileNotFoundError("vanilla-tweaks.exe was not found.")

        args = [tweaks_exe]

        if modern_cli:
            # tubtubs/vanilla-tweaks keeps these patches opt-in.
            if abs(self.vt_fov.get() - 1.5708) >= 0.0001:
                args.extend(["--fov", str(self.vt_fov.get()), "--fov-patch"])

            if self.vt_farclip.get() == 777:
                args.append("--no-farclip")
            else:
                args.extend(["--farclip", str(self.vt_farclip.get())])

            if self.vt_frill.get() == 70:
                args.append("--no-frilldistance")
            else:
                args.extend(["--frilldistance", str(self.vt_frill.get())])

            if self.vt_nameplate.get() == 20:
                args.append("--no-nameplatedistance")
            else:
                args.extend(["--nameplatedistance", str(self.vt_nameplate.get())])

            if self.vt_soundchan.get() != 12:
                args.extend([
                    "--soundchannels",
                    str(self.vt_soundchan.get()),
                    "--soundchannels-patch",
                ])

            if self.vt_maxcam.get() != 50:
                args.extend(["--maxcameradistance", str(self.vt_maxcam.get())])

            if self.vt_quickloot.get():
                args.append("--quickloot")
            if self.vt_bg_sound.get():
                args.append("--sound-in-background")
            if not self.vt_laa.get():
                args.append("--no-largeaddressaware")
            if not self.vt_cam_fix.get():
                args.append("--no-cameraskipfix")
            if self.vt_crossfaction_res.get():
                args.append("--crossfactionresfix")
            if not self.vt_custom_glues.get():
                args.append("--no-customgluespatch")
            if not self.vt_bluemoon.get():
                args.append("--no-bluemoonpatch")
        else:
            # Legacy bundled brndd patcher kept only as an offline fallback.
            if abs(self.vt_fov.get() - 1.5708) < 0.0001:
                args.append("--no-fov")
            else:
                args.extend(["--fov", str(self.vt_fov.get())])

            if self.vt_soundchan.get() == 12:
                args.append("--no-soundchannels")
            else:
                args.extend(["--soundchannels", str(self.vt_soundchan.get())])

            if not self.vt_quickloot.get():
                args.append("--no-quickloot")
            if not self.vt_bg_sound.get():
                args.append("--no-sound-in-background")

            if self.vt_farclip.get() == 777:
                args.append("--no-farclip")
            else:
                args.extend(["--farclip", str(self.vt_farclip.get())])

            if self.vt_frill.get() == 70:
                args.append("--no-frilldistance")
            else:
                args.extend(["--frilldistance", str(self.vt_frill.get())])

            if self.vt_nameplate.get() == 20:
                args.append("--no-nameplatedistance")
            else:
                args.extend(["--nameplatedistance", str(self.vt_nameplate.get())])

            if self.vt_maxcam.get() != 50:
                args.extend(["--maxcameradistance", str(self.vt_maxcam.get())])

            if not self.vt_laa.get():
                args.append("--no-largeaddressaware")
            if not self.vt_cam_fix.get():
                args.append("--no-cameraskipfix")

        output_exe = os.path.join(target, "WoW_Modernized.exe")
        staged_output = output_exe + ".modernization-new"

        # Never let a failed patcher invocation damage a working modernized
        # executable. Build to a temporary path, validate it, then commit.
        if os.path.exists(staged_output):
            try:
                os.remove(staged_output)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not prepare temporary vanilla-tweaks output: {exc}"
                ) from exc

        args.extend(["-o", staged_output])
        args.append(wow_exe)

        try:
            subprocess.run(args, check=True)

            valid_pe, reason = self._inspect_wow_executable(staged_output)
            if not valid_pe:
                raise RuntimeError(
                    "vanilla-tweaks produced an invalid WoW executable. "
                    f"{reason}"
                )

            if os.path.getsize(staged_output) < 1024 * 1024:
                raise RuntimeError(
                    "vanilla-tweaks produced an unexpectedly small WoW executable."
                )

            os.replace(staged_output, output_exe)
            return output_exe
        finally:
            if os.path.exists(staged_output):
                try:
                    os.remove(staged_output)
                except OSError:
                    pass

if __name__ == "__main__":
    root = tk.Tk()
    app = WowSetupTool(root)
    root.mainloop()
