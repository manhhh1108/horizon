"""In-tool plugin editor (PL-07) for plaintext .txt/.md plugins."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox,
)

from horizon_tool.core.plugin_manager import read_plugin_text, save_plugin_text


class PluginEditorDialog(QDialog):
    """Edit and save a plaintext plugin, backing up the previous version."""

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.setWindowTitle(f"Sửa plugin — {self.path.name}")
        self.resize(760, 640)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(read_plugin_text(self.path))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addWidget(self.editor)
        root.addWidget(buttons)

    def save(self) -> None:
        save_plugin_text(self.path, self.editor.toPlainText())
        self.accept()
