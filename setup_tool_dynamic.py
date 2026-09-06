import math
import os
import re
import stat
import struct
import sys
import tkinter as tk
import types
from tkinter import messagebox

import remote_packages
import setup_tool_dynamic_core as _dynamic_core
# Keep the feature-branch implementation intact and layer only the executable
# normalization policy here. This makes the B-total policy easy to audit and
# keeps every unrelated remote/fallback behavior byte-for-byte unchanged.
from setup_tool_dynamic_core import *  # noqa: F401,F403
from setup_tool_dynamic_core import ModernWowSetupTool as _ModernWowSetupToolCore


_CAMERA_REGIONS = (
    (
        0x02CCD0,
        bytes.fromhex(
            "55 8b ec 83 ec 10 8d 45 f0 50 33 c9 e8 4f 8f 00 "
            "00 50 ff 15 64 f6 7f 00 8b 45 f8 99 2b c2 8b c8 "
            "8b 45 fc 99 2b c2 d1 f8 d1 f9 50 51 89 0d 38 4e "
            "88 00 a3 3c 4e 88 00 ff 15 5c f6 7f 00 8b e5 5d "
            "c3 90 90"
        ),
        bytes.fromhex(
            "55 8b 05 48 4e 88 00 8b 0d 44 4e 88 00 e9 33 90 "
            "32 00 83 c0 32 83 c1 32 3b 0d a8 eb c4 00 7e 03 "
            "83 e9 01 3b 05 ac eb c4 00 7e 03 83 e8 01 83 e9 "
            "32 83 e8 32 89 05 48 4e 88 00 89 0d 44 4e 88 00 "
            "5d eb 0d"
        ),
    ),
    (
        0x02D326,
        bytes.fromhex("8b 45 f0 8b 15"),
        bytes.fromhex("e9 b1 8a 32 00"),
    ),
    (
        0x02D334,
        bytes.fromhex("8b 35 3c 4e 88 00"),
        bytes.fromhex("8b 35 48 4e 88 00"),
    ),
    (
        0x355D15,
        bytes.fromhex(
            "cc cc cc cc cc cc cc cc cc cc cc cc cc cc cc cc "
            "cc cc cc cc cc"
        ),
        bytes.fromhex(
            "83 f8 32 7d 03 83 c0 01 83 f9 32 7d 03 83 c1 01 "
            "e9 b8 6f cd ff"
        ),
    ),
    (
        0x355DDC,
        bytes.fromhex(
            "cc cc cc cc cc cc cc cc cc cc cc cc cc cc cc cc "
            "cc cc cc cc cc cc cc cc cc cc cc cc cc cc"
        ),
        bytes.fromhex(
            "8d 4d f0 51 ff 35 00 4e 88 00 ff 15 50 f6 7f 00 "
            "8b 45 f0 8b 15 44 4e 88 00 e9 35 75 cd ff"
        ),
    ),
)

_CUSTOM_GLUES_SITES = (
    (0x2F113A, 0x5F, 0xEB),
    (0x2F113B, 0x5E, 0x19),
    (0x2F1158, 0x01, 0x03),
    (0x2F11A7, 0x01, 0x03),
    (0x2F11F0, 0x5F, 0xEB),
    (0x2F11F1, 0x5E, 0xB2),
)

# Numeric fields may already contain legitimate Turtle/Octo/community values.
# Preflight only sanity-checks those fixed-offset fields; normalization later
# applies the exact Tool policy without fingerprinting community numeric values.
_NUMERIC_SITES = (
    ("fov", 0x4089B4, "FoV", 0.5, 3.5),
    ("farclip", 0x40FED8, "Farclip", 777.0, 10000.0),
    ("frill", 0x467958, "Frill Distance", 0.0, 1000.0),
    ("nameplate", 0x40C448, "Nameplate Distance", 0.0, 150.0),
    ("maxcam", 0x4089A4, "Max Camera Distance", 1.0, 250.0),
)
_SOUND_SITE = ("sound", 0x435D38, "Sound Channels", 1, 128)
_CLIENT_BUILD_OFFSET = 0x437BFC
_CLIENT_VERSION_OFFSET = 0x437C04
_CLIENT_BUILD = b"5875"
_CLIENT_VERSION = b"1.12.1"
_FARCLIP_EXE_CEILING = 3000.0


def _strict_verify_mpq(path):
    """Validate classic MPQ headers/table bounds, including user-data wrappers."""
    try:
        size = os.path.getsize(path)
        if size < 32:
            raise remote_packages.RemotePackageError(
                "Downloaded MPQ is too small to contain a valid header."
            )

        with open(path, "rb") as handle:
            prefix = handle.read(16)
            archive_base = 0

            if prefix[:4] == b"MPQ\x1B":
                if len(prefix) != 16 or size < 48:
                    raise remote_packages.RemotePackageError(
                        "Downloaded MPQ has a truncated user-data header."
                    )
                try:
                    _user_data_size, header_offset, user_header_size = (
                        struct.unpack_from("<III", prefix, 4)
                    )
                except struct.error as exc:
                    raise remote_packages.RemotePackageError(
                        "Downloaded MPQ has a malformed user-data header."
                    ) from exc
                if (
                    user_header_size < 16
                    or header_offset < user_header_size
                    or header_offset > size - 32
                ):
                    raise remote_packages.RemotePackageError(
                        "Downloaded MPQ has an invalid nested archive offset."
                    )
                if (
                    _user_data_size < user_header_size
                    or _user_data_size > header_offset
                ):
                    raise remote_packages.RemotePackageError(
                        "Downloaded MPQ has an invalid user-data size."
                    )
                archive_base = header_offset
                handle.seek(archive_base)
                header = handle.read(32)
            elif prefix[:4] == b"MPQ\x1A":
                handle.seek(0)
                header = handle.read(32)
            else:
                raise remote_packages.RemotePackageError(
                    "Downloaded file is not a valid MPQ archive."
                )
    except remote_packages.RemotePackageError:
        raise
    except OSError as exc:
        raise remote_packages.RemotePackageError(
            f"Could not inspect downloaded MPQ: {exc}"
        ) from exc

    if len(header) != 32 or header[:4] != b"MPQ\x1A":
        raise remote_packages.RemotePackageError(
            "Downloaded file is not a valid MPQ archive."
        )

    try:
        (
            header_size,
            archive_size,
            format_version,
            sector_size_shift,
            hash_table_offset,
            block_table_offset,
            hash_table_entries,
            block_table_entries,
        ) = struct.unpack_from("<IIHHIIII", header, 4)
    except struct.error as exc:
        raise remote_packages.RemotePackageError(
            "Downloaded MPQ has a truncated header."
        ) from exc

    if header_size < 32 or archive_base + header_size > size:
        raise remote_packages.RemotePackageError(
            "Downloaded MPQ has an invalid header size."
        )
    if archive_size < header_size or archive_base + archive_size > size:
        raise remote_packages.RemotePackageError(
            "Downloaded MPQ has an invalid archive size."
        )
    if format_version not in (0, 1):
        raise remote_packages.RemotePackageError(
            f"Downloaded MPQ uses unsupported format version {format_version}."
        )
    if sector_size_shift == 0 or sector_size_shift > 16:
        raise remote_packages.RemotePackageError(
            "Downloaded MPQ has an invalid sector-size shift."
        )

    tables = (
        ("hash", hash_table_offset, hash_table_entries),
        ("block", block_table_offset, block_table_entries),
    )
    for table_name, table_offset, entry_count in tables:
        if entry_count <= 0:
            raise remote_packages.RemotePackageError(
                f"Downloaded MPQ has an empty {table_name} table."
            )
        table_size = entry_count * 16
        if (
            table_offset < header_size
            or table_offset > archive_size
            or table_size > archive_size - table_offset
        ):
            raise remote_packages.RemotePackageError(
                f"Downloaded MPQ has an out-of-bounds {table_name} table."
            )


def _strict_managed_mpq_is_current(target_dir, mod_id, revision):
    if not remote_packages.managed_mod_is_current(target_dir, mod_id, revision):
        return False
    files = remote_packages._load_managed_manifest(target_dir, mod_id)
    if len(files) != 1:
        return False
    path = os.path.join(target_dir, files[0])
    try:
        _strict_verify_mpq(path)
        return True
    except remote_packages.RemotePackageError:
        return False


def _strict_managed_mpq_is_usable(target_dir, mod_id):
    if not remote_packages.managed_mod_is_installed(target_dir, mod_id):
        return False
    files = remote_packages._load_managed_manifest(target_dir, mod_id)
    if len(files) != 1:
        return False
    path = os.path.join(target_dir, files[0])
    try:
        _strict_verify_mpq(path)
        return True
    except remote_packages.RemotePackageError:
        return False


def _install_strict_mpq_runtime_hooks():
    """Enable strict MPQ checks only while the real visual installer is running.

    Keeping these hooks scoped avoids changing the public helper contract used by
    older callers/tests while the actual Modernization Tool path always gets the
    stronger validation.
    """
    originals = {
        "_verify_mpq": remote_packages._verify_mpq,
        "_download_remote_mpq": remote_packages._download_remote_mpq,
        "managed_mpq_is_current": remote_packages.managed_mpq_is_current,
        "managed_mpq_is_usable": remote_packages.managed_mpq_is_usable,
    }
    original_download_remote_mpq = originals["_download_remote_mpq"]

    def strict_download_remote_mpq(*args, **kwargs):
        temp_path = original_download_remote_mpq(*args, **kwargs)
        try:
            _strict_verify_mpq(temp_path)
        except remote_packages.RemotePackageError as exc:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            label = kwargs.get("label") or "Downloading visual mod"
            raise remote_packages.RemoteSourceUnavailable(
                f"{label}: remote source returned an invalid MPQ package ({exc})."
            ) from exc
        return temp_path

    remote_packages._verify_mpq = _strict_verify_mpq
    remote_packages._download_remote_mpq = strict_download_remote_mpq
    remote_packages.managed_mpq_is_current = _strict_managed_mpq_is_current
    remote_packages.managed_mpq_is_usable = _strict_managed_mpq_is_usable
    return originals


def _restore_mpq_runtime_hooks(originals):
    for name, value in originals.items():
        setattr(remote_packages, name, value)


class ModernWowSetupTool(_ModernWowSetupToolCore):
    """Remote-fallback tool with authoritative, fail-safe Vanilla Tweaks output."""

    def _vanilla_tweaks_signature(self):
        signature = super()._vanilla_tweaks_signature()
        # Runtime Farclip lives in Config.wtf; the executable ceiling is fixed.
        # Keep the executable signature stable when only Render Distance changes.
        signature["farclip"] = int(_FARCLIP_EXE_CEILING)
        # Bump when normalization changes so existing managed installs get one
        # clean WoW_Modernized.exe rebuild under the new policy.
        signature["selected_patch_normalization"] = 4
        signature["source_fingerprint_policy"] = 1
        return signature

    def _desired_normalized_values(self):
        selected_farclip = float(self.vt_farclip.get())
        desired = {
            "fov": float(self.vt_fov.get()),
            "farclip": selected_farclip,
            "frill": float(self.vt_frill.get()),
            "nameplate": float(self.vt_nameplate.get()),
            "maxcam": float(self.vt_maxcam.get()),
            "sound": int(self.vt_soundchan.get()),
        }

        ranges = (
            ("FoV", desired["fov"], 0.5, 3.5),
            ("Farclip", selected_farclip, 100.0, _FARCLIP_EXE_CEILING),
            ("Frill Distance", desired["frill"], 0.0, 10000.0),
            ("Nameplate Distance", desired["nameplate"], 1.0, 500.0),
            ("Max Camera Distance", desired["maxcam"], 1.0, 1000.0),
        )
        for label, value, minimum, maximum in ranges:
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise RuntimeError(
                    f"{label} value is outside the supported WoW 1.12.1 range."
                )

        sound_channels = str(desired["sound"]).encode("ascii") + b"\x00"
        if not 1 <= desired["sound"] <= 256 or len(sound_channels) > 4:
            raise RuntimeError(
                "Sound Channels value is outside the supported WoW 1.12.1 range."
            )
        desired["sound_bytes"] = sound_channels.ljust(4, b"\x00")

        # The EXE field is the maximum allowed Farclip, not the active distance.
        # Keep it fixed at 3000. The selected runtime value is synchronized to
        # Config.wtf separately and may never exceed this ceiling.
        desired["farclip"] = _FARCLIP_EXE_CEILING
        return desired

    def validate_limits(self):
        if not super().validate_limits():
            return False

        try:
            farclip = float(self.vt_farclip.get())
        except (tk.TclError, TypeError, ValueError):
            messagebox.showerror(
                "Input Error",
                "Render Distance (Farclip) must contain a valid number.",
            )
            return False

        if not math.isfinite(farclip) or not 100.0 <= farclip <= _FARCLIP_EXE_CEILING:
            messagebox.showerror(
                "Limit Exceeded",
                "Render distance (Farclip) must stay between 100 and 3000. "
                "The 3000 hard maximum also applies when Safety Limits are disabled.",
            )
            return False

        return True

    @staticmethod
    def _validate_client_identity(data):
        """Compatibility no-op: Turtle/Octo may move build/version strings."""
        del data
        return None

    def _validate_source_numeric_values(self, data):
        """Sanity-check fixed-offset numeric source values without fingerprinting them."""
        for _key, offset, label, minimum, maximum in _NUMERIC_SITES:
            raw = bytes(data[offset:offset + 4])
            value = struct.unpack("<f", raw)[0]
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise RuntimeError(
                    f"Unexpected {label} source value at 0x{offset:X}; "
                    "refusing to alter an unknown client."
                )

        _key, offset, label, minimum, maximum = _SOUND_SITE
        raw = bytes(data[offset:offset + 4])
        text, separator, tail = raw.partition(b"\x00")
        if not separator or not text.isdigit() or any(tail):
            raise RuntimeError(
                f"Unexpected {label} source bytes at 0x{offset:X}; "
                "refusing to alter an unknown client."
            )
        value = int(text)
        if not minimum <= value <= maximum:
            raise RuntimeError(
                f"Unexpected {label} source value at 0x{offset:X}; "
                "refusing to alter an unknown client."
            )

    def _validate_vanilla_tweaks_state(
        self,
        data,
        *,
        allow_foreign_custom_glues=False,
        accepted_custom_glues=None,
    ):
        """Validate every non-numeric region the B-total policy may rewrite.

        Returns a foreign Custom GlueXML byte tuple only during source preflight.
        Such a tuple is treated as client-owned code and later restored exactly.
        """
        required_size = 0x46795C
        if len(data) < required_size:
            raise RuntimeError(
                "WoW.exe is too small for Vanilla Tweaks safety preflight."
            )

        quickloot_sites = (
            (0x0C1ECF, 0x10),
            (0x0C2B25, 0x0B),
        )
        for offset, displacement in quickloot_sites:
            current = bytes(data[offset:offset + 2])
            known = (
                bytes((0x74, displacement)),
                bytes((0x75, displacement)),
                b"\x90\x90",
            )
            if current not in known:
                raise RuntimeError(
                    f"Unexpected QuickLoot bytes at 0x{offset:X}; "
                    "refusing to alter an unknown client."
                )

        if data[0x3A4869] not in (0x14, 0x27):
            raise RuntimeError(
                "Unexpected Background Sound byte; refusing to alter an unknown client."
            )

        laa_current = bytes(data[0x126:0x128])
        if laa_current not in (b"\x0F\x01", b"\x2F\x01"):
            raise RuntimeError(
                "Unexpected Large Address Aware bytes; refusing to alter an unknown client."
            )

        for offset, original, patched in _CAMERA_REGIONS:
            current = bytes(data[offset:offset + len(original)])
            if current not in (original, patched):
                raise RuntimeError(
                    f"Unexpected Camera Skip Fix bytes at 0x{offset:X}; "
                    "refusing to alter an unknown client."
                )

        custom_state = tuple(
            data[offset] for offset, _original, _patched in _CUSTOM_GLUES_SITES
        )
        custom_original = tuple(
            original for _offset, original, _patched in _CUSTOM_GLUES_SITES
        )
        custom_patched = tuple(
            patched for _offset, _original, patched in _CUSTOM_GLUES_SITES
        )
        foreign_custom_glues = None
        accepted_custom = (
            tuple(accepted_custom_glues)
            if accepted_custom_glues is not None
            else None
        )
        if custom_state not in (custom_original, custom_patched):
            if accepted_custom is not None and custom_state == accepted_custom:
                pass
            elif allow_foreign_custom_glues:
                # Turtle/Octo and other compatible clients may legitimately own
                # this loader region. Never classify those bytes as vanilla and
                # never overwrite them just to satisfy the checkbox state.
                foreign_custom_glues = custom_state
            else:
                raise RuntimeError(
                    "Unexpected Custom GlueXML bytes; refusing to alter an unknown client."
                )

        return foreign_custom_glues

    def _preflight_vanilla_tweaks_source(self, target):
        """Read and validate WoW.exe before vanilla-tweaks or any install write runs."""
        self._vt_preserved_custom_glues = None
        wow_exe = os.path.join(target, "WoW.exe")
        try:
            with open(wow_exe, "rb") as handle:
                data = bytearray(handle.read())
        except OSError as exc:
            raise RuntimeError(
                "Could not inspect WoW.exe for Vanilla Tweaks safety preflight."
            ) from exc

        self._desired_normalized_values()
        preserved = self._validate_vanilla_tweaks_state(
            data,
            allow_foreign_custom_glues=True,
        )
        self._validate_client_identity(data)
        self._validate_source_numeric_values(data)
        self._vt_preserved_custom_glues = preserved
        return preserved

    def validate_plugin_conflicts(self):
        """Use the installer's final read-only validation gate for EXE preflight."""
        if not super().validate_plugin_conflicts():
            return False

        target = self.wow_dir.get().strip()
        try:
            self._preflight_vanilla_tweaks_source(target)
        except Exception as exc:
            messagebox.showerror(
                "Vanilla Tweaks safety check",
                f"{exc}\n\nNo installation files were changed.",
            )
            return False
        return True

    def configure_visual_audio(self, target):
        """Run every visual MPQ path with strict archive validation enabled."""
        originals = _install_strict_mpq_runtime_hooks()
        try:
            return super().configure_visual_audio(target)
        finally:
            _restore_mpq_runtime_hooks(originals)

    def _configure_superwow_fov_cvar(self, target):
        """Keep SuperWoW's FoV CVar aligned with the Tool-selected FoV."""
        superwow = self.core_plugins.get("SuperWoWhook.dll")
        if superwow is None or not superwow.get():
            return

        try:
            fov = float(self.vt_fov.get())
        except (TypeError, ValueError, tk.TclError) as exc:
            raise RuntimeError("Field of View is not a valid numeric value.") from exc
        if not math.isfinite(fov) or not 0.5 <= fov <= 3.5:
            raise RuntimeError(
                "Field of View value is outside the supported WoW 1.12.1 range."
            )

        wtf_dir = os.path.join(target, "WTF")
        config_path = os.path.join(wtf_dir, "Config.wtf")
        original_mode = None
        restore_readonly = False
        staged = config_path + ".modernization-fov"

        try:
            os.makedirs(wtf_dir, exist_ok=True)

            if os.path.exists(config_path):
                original_mode = os.stat(config_path).st_mode
                if not (original_mode & stat.S_IWRITE):
                    os.chmod(config_path, original_mode | stat.S_IWRITE)
                    restore_readonly = True

            existing = ""
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8", errors="ignore") as handle:
                    existing = handle.read()

            setting = f'SET FoV "{format(fov, ".9g")}"'
            pattern = re.compile(
                r'^\s*SET\s+FoV\s+"[^"]*"\s*$',
                re.IGNORECASE | re.MULTILINE,
            )
            if pattern.search(existing):
                updated = pattern.sub(setting, existing)
            else:
                if existing and not existing.endswith(("\n", "\r")):
                    existing += "\n"
                updated = existing + setting + "\n"

            with open(staged, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
            os.replace(staged, config_path)

        except PermissionError as exc:
            raise RuntimeError(
                "Windows denied access to WTF\\Config.wtf while synchronizing "
                "the SuperWoW FoV. Close WoW and any program using the file, "
                "then try again."
            ) from exc
        finally:
            if os.path.exists(staged):
                try:
                    os.remove(staged)
                except OSError:
                    pass
            if restore_readonly and original_mode is not None and os.path.exists(config_path):
                try:
                    os.chmod(config_path, original_mode)
                except OSError:
                    pass

    def _configure_farclip_cvar(self, target):
        """Synchronize the Tool-selected runtime Farclip to WTF/Config.wtf."""
        try:
            farclip = int(self.vt_farclip.get())
        except (tk.TclError, TypeError, ValueError) as exc:
            raise RuntimeError("Render Distance (Farclip) is not a valid number.") from exc
        if not 100 <= farclip <= int(_FARCLIP_EXE_CEILING):
            raise RuntimeError(
                "Render Distance (Farclip) must stay between 100 and 3000."
            )

        wtf_dir = os.path.join(target, "WTF")
        config_path = os.path.join(wtf_dir, "Config.wtf")
        staged = config_path + ".modernization-farclip"
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
                with open(config_path, "r", encoding="utf-8", errors="ignore") as handle:
                    existing = handle.read()

            setting = f'SET farclip "{farclip}"'
            pattern = re.compile(
                r'^\s*SET\s+farclip\s+"[^"]*"\s*$',
                re.IGNORECASE | re.MULTILINE,
            )
            if pattern.search(existing):
                updated = pattern.sub(setting, existing)
            else:
                if existing and not existing.endswith(("\n", "\r")):
                    existing += "\n"
                updated = existing + setting + "\n"

            with open(staged, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
            os.replace(staged, config_path)

        except OSError as exc:
            raise RuntimeError(
                "Could not synchronize Render Distance in WTF\\Config.wtf. "
                "Close WoW and any program using the file, then try again."
            ) from exc
        finally:
            if os.path.exists(staged):
                try:
                    os.remove(staged)
                except OSError:
                    pass
            if restore_readonly and original_mode is not None and os.path.exists(config_path):
                try:
                    os.chmod(config_path, original_mode)
                except OSError:
                    pass

    def configure_script_memory(self, target):
        """Apply base Config.wtf settings, then synchronize FoV and Farclip."""
        super().configure_script_memory(target)
        self._configure_superwow_fov_cvar(target)
        self._configure_farclip_cvar(target)

    def run_installation(self):
        """Run the EXE patch transaction before the installer's first file write.

        The base installer intentionally remains untouched. We intercept its
        first mutating step (clean_unselected_files), run Vanilla Tweaks once,
        then make the later vanilla-tweaks slot a no-op for this Apply.
        """
        previous_clean = self.__dict__.get("clean_unselected_files")
        previous_vt = self.__dict__.get("run_vanilla_tweaks")
        had_clean_override = "clean_unselected_files" in self.__dict__
        had_vt_override = "run_vanilla_tweaks" in self.__dict__

        real_clean = self.clean_unselected_files
        real_vt = self.run_vanilla_tweaks
        state = {"ran": False, "result": None}

        def run_vt_once(target):
            if not state["ran"]:
                state["result"] = real_vt(target)
                state["ran"] = True
            return state["result"]

        def clean_after_vt(target):
            run_vt_once(target)
            return real_clean(target)

        self.__dict__["clean_unselected_files"] = clean_after_vt
        self.__dict__["run_vanilla_tweaks"] = run_vt_once
        try:
            return super().run_installation()
        finally:
            if had_clean_override:
                self.__dict__["clean_unselected_files"] = previous_clean
            else:
                self.__dict__.pop("clean_unselected_files", None)
            if had_vt_override:
                self.__dict__["run_vanilla_tweaks"] = previous_vt
            else:
                self.__dict__.pop("run_vanilla_tweaks", None)

    def _run_vanilla_tweaks_transactional(
        self,
        target,
        tweaks_exe,
        modern_cli=True,
    ):
        """Recheck the source immediately before the staged patch transaction."""
        self._preflight_vanilla_tweaks_source(target)
        return super()._run_vanilla_tweaks_transactional(
            target,
            tweaks_exe=tweaks_exe,
            modern_cli=modern_cli,
        )

    def _normalize_selected_vanilla_tweaks_output(self, output_exe):
        """Make Tool-owned executable tweaks authoritative on pre-patched clients.

        Blue Moon and Cross-faction Resurrection deliberately keep the previous
        vanilla-tweaks behavior. A foreign Custom GlueXML region discovered on
        the original WoW.exe is also preserved byte-for-byte because community
        clients may use those offsets for their own loader/anti-tamper code.
        """
        try:
            with open(output_exe, "rb") as handle:
                data = bytearray(handle.read())
        except OSError as exc:
            raise RuntimeError(
                "Could not inspect WoW_Modernized.exe for Vanilla Tweaks normalization."
            ) from exc

        preserved_custom_glues = getattr(
            self,
            "_vt_preserved_custom_glues",
            None,
        )
        self._validate_vanilla_tweaks_state(
            data,
            accepted_custom_glues=preserved_custom_glues,
        )
        desired = self._desired_normalized_values()

        # Numeric fields are intentionally not fingerprinted after vanilla-tweaks.
        # Their source values were sanity-checked during preflight and the Tool
        # overwrites them below with the exact values selected by the user.

        # All validation passed. Apply the exact Tool selections in memory.
        quickloot_sites = (
            (0x0C1ECF, 0x10),
            (0x0C2B25, 0x0B),
        )
        desired_quickloot_opcode = 0x75 if self.vt_quickloot.get() else 0x74
        for offset, displacement in quickloot_sites:
            data[offset:offset + 2] = bytes(
                (desired_quickloot_opcode, displacement)
            )

        data[0x3A4869] = 0x27 if self.vt_bg_sound.get() else 0x14
        data[0x126:0x128] = b"\x2F\x01" if self.vt_laa.get() else b"\x0F\x01"

        desired_camera_patched = bool(self.vt_cam_fix.get())
        for offset, original, patched in _CAMERA_REGIONS:
            selected = patched if desired_camera_patched else original
            data[offset:offset + len(selected)] = selected

        if preserved_custom_glues is not None:
            # The original client owned this region. vanilla-tweaks may have
            # rewritten it in staging, so put the exact source bytes back.
            for index, (offset, _original, _patched) in enumerate(_CUSTOM_GLUES_SITES):
                data[offset] = preserved_custom_glues[index]
        else:
            desired_custom_patched = bool(self.vt_custom_glues.get())
            for offset, original, patched in _CUSTOM_GLUES_SITES:
                data[offset] = patched if desired_custom_patched else original

        struct.pack_into("<f", data, 0x4089B4, desired["fov"])
        struct.pack_into("<f", data, 0x40FED8, desired["farclip"])
        struct.pack_into("<f", data, 0x467958, desired["frill"])
        struct.pack_into("<f", data, 0x40C448, desired["nameplate"])
        struct.pack_into("<f", data, 0x4089A4, desired["maxcam"])
        data[0x435D38:0x435D3C] = desired["sound_bytes"]

        # Blue Moon (0x3E5B83) and Cross-faction Res (0x2067DE) are intentionally
        # not normalized here. vanilla-tweaks keeps exactly the previous behavior
        # for those two options.

        staged = output_exe + ".modernization-normalized"
        try:
            with open(staged, "wb") as handle:
                handle.write(data)
            os.replace(staged, output_exe)
        except OSError as exc:
            raise RuntimeError(
                "Could not write the normalized WoW_Modernized.exe."
            ) from exc
        finally:
            if os.path.exists(staged):
                try:
                    os.remove(staged)
                except OSError:
                    pass


class _DynamicModuleProxy(types.ModuleType):
    """Keep legacy module-level monkey patches visible to the preserved core."""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == "get_base_path":
            setattr(_dynamic_core, name, value)


# Existing tests and external callers historically patched
# setup_tool_dynamic.get_base_path. Preserve that behavior after splitting the
# untouched implementation into setup_tool_dynamic_core.py.
sys.modules[__name__].__class__ = _DynamicModuleProxy


if __name__ == "__main__":
    root = tk.Tk()
    app = ModernWowSetupTool(root)
    root.mainloop()
