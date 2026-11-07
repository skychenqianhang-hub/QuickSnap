"""The settings window: shortcut, screenshot folder, start with Windows, language.

Every change applies immediately (no Save / OK button). Each row has a small status
line underneath that says whether it worked.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import hotkey, i18n, win32
from .i18n import tr
from .icon import app_icon
from .version import __version__

OK_COLOR = "#2e9e44"     # readable on light and dark window backgrounds
ERR_COLOR = "#d9453c"


def _mods_from_qt(mods) -> int:
    out = 0
    if mods & Qt.KeyboardModifier.ControlModifier:
        out |= win32.MOD_CONTROL
    if mods & Qt.KeyboardModifier.AltModifier:
        out |= win32.MOD_ALT
    if mods & Qt.KeyboardModifier.ShiftModifier:
        out |= win32.MOD_SHIFT
    if mods & Qt.KeyboardModifier.MetaModifier:  # the Windows key
        out |= win32.MOD_WIN
    return out


def _partial(mods: int) -> str:
    names = [n for n, m in [("Ctrl", win32.MOD_CONTROL), ("Alt", win32.MOD_ALT),
                            ("Shift", win32.MOD_SHIFT), ("Win", win32.MOD_WIN)] if mods & m]
    return "+".join(names + ["…"]) if names else ""


class HotkeyEdit(QLineEdit):
    """Click it, press a key combination, done. Esc (or clicking elsewhere) keeps the old one."""

    started = Signal()            # user clicked in: the old shortcut is paused meanwhile
    cancelled = Signal()          # left without choosing
    chosen = Signal(str)          # e.g. "Ctrl+Shift+X"
    rejected = Signal(str)        # translated reason, e.g. "Add Ctrl, Alt or Win…"

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)                # no typing; we read key presses ourselves
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(170)
        self._old = text
        self._capturing = False

    def set_shortcut(self, text: str) -> None:
        self._old = text
        if not self._capturing:
            self.setText(text)

    def _listening(self, on: bool) -> None:
        """While listening: blue outline and the words 'Press the new shortcut…' in the box."""
        self._capturing = on
        self.setStyleSheet("QLineEdit { border: 2px solid #2F9BFF; border-radius: 4px; padding: 3px; }"
                           if on else "")
        self.setText(tr("Press the new shortcut…") if on else self._old)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._listening(True)
        self.started.emit()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if self._capturing:
            self._listening(False)
            self.cancelled.emit()

    def keyPressEvent(self, e):
        if not self._capturing:
            return
        mods = _mods_from_qt(e.modifiers())
        if e.key() == Qt.Key.Key_Escape and not mods:
            self.clearFocus()                 # -> cancelled
            return
        vk = e.nativeVirtualKey() or hotkey.vk_from_qt(e.key())
        if vk in hotkey.MODIFIER_VKS or e.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt,
                                                    Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            self.setText(_partial(mods))      # show "Ctrl+Alt+…" while keys are held
            return
        problem = hotkey.problem_with(mods, vk)
        if problem:
            self.setText(tr("Press the new shortcut…"))
            self.rejected.emit(tr(problem))
            return
        text = hotkey.text_from(mods, vk)
        self._old = text
        self._listening(False)
        self.chosen.emit(text)
        self.clearFocus()

    def keyReleaseEvent(self, e):
        if self._capturing and not _mods_from_qt(e.modifiers()):
            self.setText(tr("Press the new shortcut…"))


class SettingsWindow(QWidget):
    closed = Signal()

    def __init__(self, controller):
        super().__init__(None)
        self.c = controller
        self.setWindowTitle(tr("QuickSnap Settings"))
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)  # nothing to maximize
        self.setMinimumWidth(560)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # --- shortcut
        self.hotkey_edit = HotkeyEdit(controller.hotkey_text())
        self.hotkey_edit.started.connect(self._hotkey_started)
        self.hotkey_edit.cancelled.connect(self._hotkey_cancelled)
        self.hotkey_edit.chosen.connect(self._hotkey_chosen)
        self.hotkey_edit.rejected.connect(lambda msg: self._status(self.hotkey_status, msg, False))
        reset = QPushButton(tr("Restore default"))
        reset.setToolTip(tr("Back to {0}", controller.default_hotkey()))
        reset.clicked.connect(lambda: self._hotkey_chosen(controller.default_hotkey()))
        row = QHBoxLayout()
        row.addWidget(self.hotkey_edit)
        row.addWidget(reset)
        row.addStretch(1)
        self.hotkey_status = self._status_label()
        form.addRow(tr("Screenshot shortcut"), row)
        form.addRow("", self.hotkey_status)
        if controller.hotkey_ok:
            self._status(self.hotkey_status, tr("Click the box, then press the keys you want."), None)
        else:
            self._status(self.hotkey_status, tr("{0} is used by another program. Choose another one.",
                                                controller.hotkey_text()), False)

        # --- folder
        self.folder_edit = QLineEdit(str(controller.save_dir()))
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        change = QPushButton(tr("Change…"))
        change.clicked.connect(self._choose_folder)
        open_btn = QPushButton(tr("Open"))
        open_btn.clicked.connect(controller.open_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder_edit, 1)
        row.addWidget(change)
        row.addWidget(open_btn)
        self.folder_status = self._status_label()
        self._status(self.folder_status, tr("Used by “Save”. “Save as…” lets you pick any folder each time."),
                     None)
        form.addRow(tr("Screenshot folder"), row)
        form.addRow("", self.folder_status)

        # --- start with Windows
        self.autostart_box = QCheckBox(tr("Start QuickSnap in the tray when I sign in to Windows"))
        self.autostart_box.setChecked(controller.autostart_enabled())
        self.autostart_box.toggled.connect(self._autostart_toggled)
        self.autostart_status = self._status_label()
        form.addRow(tr("Start with Windows"), self.autostart_box)
        form.addRow("", self.autostart_status)
        self.autostart_status.hide()

        # --- language
        self.lang_box = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_box.addItem(name, code)
        self.lang_box.setCurrentIndex(list(i18n.LANGUAGES).index(i18n.current_language()))
        self.lang_box.currentIndexChanged.connect(
            lambda i: controller.set_language(self.lang_box.itemData(i)))
        row = QHBoxLayout()
        row.addWidget(self.lang_box)
        row.addStretch(1)
        form.addRow(tr("Language"), row)

        # --- bottom row
        version = QLabel(f"QuickSnap {__version__}")
        version.setEnabled(False)
        close = QPushButton(tr("Close"))
        close.setDefault(True)
        close.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(version)
        bottom.addStretch(1)
        bottom.addWidget(close)

        note = QLabel(tr("Changes apply right away. Closing this window keeps QuickSnap running in the tray."))
        note.setWordWrap(True)
        note.setEnabled(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.setSpacing(12)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addLayout(bottom)
        close.setFocus()  # not the shortcut box, or it would start listening straight away

    # ---- helpers

    @staticmethod
    def _status_label() -> QLabel:
        lab = QLabel()
        lab.setWordWrap(True)
        lab.setMinimumWidth(400)  # use the whole row; a narrow wrapped label gets cut off
        lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        f = lab.font()
        f.setPointSizeF(f.pointSizeF() * 0.92)
        lab.setFont(f)
        return lab

    @staticmethod
    def _status(label: QLabel, text: str, ok: bool | None) -> None:
        """ok=True green, ok=False red, None = plain grey hint."""
        label.setText(text)
        label.setEnabled(ok is not None)
        label.setStyleSheet("" if ok is None else f"color: {OK_COLOR if ok else ERR_COLOR};")
        label.show()

    # ---- shortcut

    def _hotkey_started(self):
        self.c.pause_hotkey()
        self._status(self.hotkey_status, tr("Press the keys now, e.g. Ctrl+Alt+A. Esc keeps the current one. "
                                                  "If nothing shows up, another program has that combination."),
                     None)

    def _hotkey_cancelled(self):
        self.c.resume_hotkey()
        if self.c.hotkey_ok:
            self._status(self.hotkey_status, tr("Unchanged: {0}", self.c.hotkey_text()), None)

    def _hotkey_chosen(self, text: str):
        error = self.c.set_hotkey(text)
        self.hotkey_edit.set_shortcut(self.c.hotkey_text())
        if error:
            self._status(self.hotkey_status, error, False)
        else:
            self._status(self.hotkey_status, tr("Done. Press {0} to take a screenshot.", self.c.hotkey_text()),
                         True)

    # ---- folder

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr("Choose the screenshot folder"),
                                                str(self.c.save_dir()))
        if not path:
            return
        error = self.c.set_save_dir(path)
        self.folder_edit.setText(str(self.c.save_dir()))
        if error:
            self._status(self.folder_status, error, False)
        else:
            self._status(self.folder_status, tr("Done. New screenshots go to this folder."), True)

    # ---- start with Windows

    def _autostart_toggled(self, on: bool):
        error = self.c.set_autostart(on)
        self.autostart_box.blockSignals(True)
        self.autostart_box.setChecked(self.c.autostart_enabled())
        self.autostart_box.blockSignals(False)
        if error:
            self._status(self.autostart_status, error, False)
        else:
            self._status(self.autostart_status,
                         tr("On. QuickSnap will start by itself next time you sign in.") if on
                         else tr("Off. Start QuickSnap yourself when you need it."), True)

    def closeEvent(self, e):
        if self.hotkey_edit.hasFocus():
            self.hotkey_edit.clearFocus()  # make sure a paused shortcut comes back
        self.closed.emit()
        super().closeEvent(e)
