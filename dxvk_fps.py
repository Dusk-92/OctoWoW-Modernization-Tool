import os
import re


DEFAULT_REFRESH_RATE = 60
_MAX_FRAME_RATE_RE = re.compile(
    r"^\s*(?P<comment>#\s*)?d3d9\.maxFrameRate\s*=\s*(?P<value>\d+)\s*$",
    re.IGNORECASE,
)


def detect_max_refresh_rate(default=DEFAULT_REFRESH_RATE):
    """Return the highest refresh rate reported by active Windows displays."""
    try:
        fallback = max(1, int(default))
    except (TypeError, ValueError):
        fallback = DEFAULT_REFRESH_RATE

    if os.name != "nt":
        return fallback

    try:
        import ctypes
        from ctypes import wintypes

        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]

        class POINTL(ctypes.Structure):
            _fields_ = [
                ("x", wintypes.LONG),
                ("y", wintypes.LONG),
            ]

        class DEVMODEW(ctypes.Structure):
            _fields_ = [
                ("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPosition", POINTL),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", wintypes.SHORT),
                ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT),
                ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD),
            ]

        enum_display_devices = ctypes.windll.user32.EnumDisplayDevicesW
        enum_display_settings = ctypes.windll.user32.EnumDisplaySettingsW
        enum_display_devices.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(DISPLAY_DEVICEW),
            wintypes.DWORD,
        ]
        enum_display_devices.restype = wintypes.BOOL
        enum_display_settings.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(DEVMODEW),
        ]
        enum_display_settings.restype = wintypes.BOOL

        DISPLAY_DEVICE_ACTIVE = 0x00000001
        ENUM_CURRENT_SETTINGS = 0xFFFFFFFF
        rates = []
        index = 0

        while True:
            device = DISPLAY_DEVICEW()
            device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if not enum_display_devices(None, index, ctypes.byref(device), 0):
                break
            index += 1

            if not (device.StateFlags & DISPLAY_DEVICE_ACTIVE):
                continue

            mode = DEVMODEW()
            mode.dmSize = ctypes.sizeof(DEVMODEW)
            if not enum_display_settings(
                device.DeviceName,
                ENUM_CURRENT_SETTINGS,
                ctypes.byref(mode),
            ):
                continue

            refresh_rate = int(mode.dmDisplayFrequency)
            # Windows may report 0/1 when the rate is unknown/default.
            if 1 < refresh_rate < 10000:
                rates.append(refresh_rate)

        if rates:
            return max(rates)
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    return fallback


def read_dxvk_fps_limit(config_path):
    """Return (enabled, fps) for the first DXVK maxFrameRate line, or None."""
    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None

    for line in lines:
        match = _MAX_FRAME_RATE_RE.match(line)
        if match is None:
            continue
        try:
            value = int(match.group("value"))
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        return match.group("comment") is None, value
    return None


def apply_dxvk_fps_limit(config_path, enabled, fps):
    """Atomically set or comment DXVK's d3d9.maxFrameRate option."""
    try:
        value = int(fps)
    except (TypeError, ValueError) as exc:
        raise ValueError("DXVK FPS limit must be a positive integer.") from exc
    if value <= 0:
        raise ValueError("DXVK FPS limit must be a positive integer.")

    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as handle:
            existing = handle.read()
    except OSError as exc:
        raise RuntimeError(f"Could not read dxvk.conf: {exc}") from exc

    setting = (
        f"d3d9.maxFrameRate = {value}"
        if enabled
        else f"# d3d9.maxFrameRate = {value}"
    )

    output = []
    replaced = False
    for line in existing.splitlines():
        if _MAX_FRAME_RATE_RE.match(line):
            if not replaced:
                output.append(setting)
                replaced = True
            # Drop duplicate maxFrameRate lines so only one setting can win.
            continue
        output.append(line)

    if not replaced:
        if output and output[-1] != "":
            output.append("")
        output.append(setting)

    updated = "\n".join(output) + "\n"
    staged = config_path + ".modernization-new"
    try:
        with open(staged, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        os.replace(staged, config_path)
    except OSError as exc:
        raise RuntimeError(f"Could not update dxvk.conf: {exc}") from exc
    finally:
        if os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass
