# 🛠️ WoW Modernization Tool v2.3

This update focuses on **better compatibility, safer WoW.exe patching, improved recovery, display-scaling support and DXVK configuration**.

## ⚙️ Vanilla Tweaks & Compatibility

- Reworked Vanilla Tweaks handling for better compatibility with **Vanilla, Turtle WoW, OctoWoW and compatible clients**.
- `WoW_Modernized.exe` is now built and validated transactionally before replacing the previous version.
- Vanilla Tweaks now runs before other installation changes.
- Improved support for already-patched clients while preserving client-specific loader code.
- Removed overly strict build/version checks that could reject compatible clients.
- SuperWoW now uses the same FoV selected by the Modernization Tool by synchronizing the `FoV` CVar in `WTF/Config.wtf`.

## 🎨 MPQ & Recovery

- Improved MPQ validation to reject corrupted or invalid archives.
- Existing valid files can now be preserved when a remote source is temporarily unavailable.
- Improved offline recovery for supported components.
- Better handling of local installation and permission errors.

## 🛡️ Reliability

- Added an optional **DXVK FPS limiter** that detects the highest refresh rate of attached displays, prefills that value and remains manually editable.
- The DXVK FPS limiter is enabled by default for new configurations, persists per WoW installation and is disabled in DirectX 9 mode.
- DXVK exclusive fullscreen is now disabled by default to avoid black screens during Alt+Tab on Windows.
- The Tool window now adapts better to Windows display scaling and smaller screens, keeping **Apply Setup & Tweaks** accessible.
- Expanded automated tests for installation ordering, recovery, executable patching and DXVK FPS configuration.
- Improved rollback behavior to reduce the risk of partial installations.

## ✅ Updating from v2.2

Download the new executable, select your existing WoW folder and click **Apply Setup & Tweaks**.

A complete WoW reinstall is not required.
