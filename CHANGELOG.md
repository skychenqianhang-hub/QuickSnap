# Changelog

## 1.0.1 — 2026-11-08

- Faster start of a screenshot: the capture windows are now prepared once, right after
  QuickSnap starts, and reused. The first screenshot after start-up no longer pays about
  half a second for loading fonts and building the windows. Costs about 10 MB of memory.
- A small timing log, `%APPDATA%\QuickSnap\timing.log`, records how long each step of a
  screenshot took (times only, never picture content) to track down slow starts.
  It keeps itself under about 100 KB.

## 1.0.0 — 2026-11-07

First release with a Windows installer.

- Runs in the system tray; closing windows never quits it.
- One global shortcut (default `Ctrl+Alt+A`, changeable in Settings) dims every monitor:
  - hover highlights the window under the mouse, a click takes that window
    (or the whole screen on the empty desktop);
  - drag to draw your own box; drag the 8 handles to resize, drag inside to move,
    arrow keys nudge it (Shift = 10 px);
  - toolbar: Copy / Save / Save as… / Cancel — every option except Cancel also copies to the clipboard.
- 5x magnifier next to the pointer with the exact pixel position and `#RRGGBB` colour;
  `Ctrl+C` copies the colour, arrow keys move the pointer one pixel at a time.
- Correct position and sharp output on multiple monitors and with 125% / 150% scaling.
- Settings window (tray menu, or start QuickSnap.exe again): shortcut with conflict check,
  screenshot folder, start with Windows, language (English / 简体中文 / 日本語).
- Installer: per-user (no administrator rights), asks for the screenshot folder
  (a non-system drive is preferred) and whether to start with Windows.
  Uninstalling keeps your screenshots and settings.
