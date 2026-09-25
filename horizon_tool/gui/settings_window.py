"""Settings dialog: edit the runtime knobs in config.yaml (Vietnamese UI)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QDialogButtonBox, QSpinBox, QComboBox,
    QCheckBox, QLineEdit,
)

from horizon_tool.core.config_loader import AppConfig, save_config


class SettingsWindow(QDialog):
    """Edits a subset of config.yaml and saves it (comment-preserving)."""

    def __init__(self, config: AppConfig, config_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path)
        self._cfg = deepcopy(config.raw)
        self.setWindowTitle("Cài đặt")
        self.resize(460, 460)

        form = QFormLayout()
        c, t, r, d, g, ar = (self._cfg.get(k, {}) for k in
                             ("chatgpt", "timeouts", "retry", "delays", "grok", "auto_resume"))

        self.send_mode = QComboBox()
        self.send_mode.addItems(["two_messages", "combined"])
        self.send_mode.setCurrentText(c.get("send_mode", "two_messages"))
        self.runtime_suffix = QLineEdit(c.get("runtime_suffix", ""))

        def spin(val, lo, hi):
            sb = QSpinBox(); sb.setRange(lo, hi); sb.setValue(int(val)); return sb

        self.element_wait = spin(t.get("element_wait_seconds", 30), 1, 600)
        self.response_wait = spin(t.get("response_wait_seconds", 600), 1, 3600)
        self.max_attempts = spin(r.get("max_attempts", 3), 1, 10)
        self.backoff = spin(r.get("backoff_base_seconds", 5), 0, 120)
        self.steps_min = spin(d.get("between_steps_min_seconds", 2), 0, 600)
        self.steps_max = spin(d.get("between_steps_max_seconds", 6), 0, 600)
        self.scripts_min = spin(d.get("between_scripts_min_seconds", 5), 0, 3600)
        self.scripts_max = spin(d.get("between_scripts_max_seconds", 15), 0, 3600)
        self.render_timeout = spin(g.get("render_timeout_seconds", 600), 10, 3600)
        self.auto_enabled = QCheckBox("Bật tự động Resume")
        self.auto_enabled.setChecked(bool(ar.get("enabled")))
        self.auto_interval = spin(ar.get("check_interval_minutes", 30), 1, 240)

        form.addRow("Cách gửi (ChatGPT):", self.send_mode)
        form.addRow("Chỉ dẫn phụ (runtime suffix):", self.runtime_suffix)
        form.addRow("Timeout chờ phần tử (s):", self.element_wait)
        form.addRow("Timeout chờ phản hồi (s):", self.response_wait)
        form.addRow("Số lần thử lại:", self.max_attempts)
        form.addRow("Backoff cơ bản (s):", self.backoff)
        form.addRow("Trễ giữa bước — nhỏ nhất (s):", self.steps_min)
        form.addRow("Trễ giữa bước — lớn nhất (s):", self.steps_max)
        form.addRow("Trễ giữa kịch bản — nhỏ nhất (s):", self.scripts_min)
        form.addRow("Trễ giữa kịch bản — lớn nhất (s):", self.scripts_max)
        form.addRow("Timeout render video Grok (s):", self.render_timeout)
        form.addRow("", self.auto_enabled)
        form.addRow("Chu kỳ tự động Resume (phút):", self.auto_interval)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def collect(self) -> dict:
        """Return an updated config dict from the form values."""
        cfg = deepcopy(self._cfg)
        cfg.setdefault("chatgpt", {})["send_mode"] = self.send_mode.currentText()
        cfg["chatgpt"]["runtime_suffix"] = self.runtime_suffix.text()
        cfg.setdefault("timeouts", {})["element_wait_seconds"] = self.element_wait.value()
        cfg["timeouts"]["response_wait_seconds"] = self.response_wait.value()
        cfg.setdefault("retry", {})["max_attempts"] = self.max_attempts.value()
        cfg["retry"]["backoff_base_seconds"] = self.backoff.value()
        dd = cfg.setdefault("delays", {})
        dd["between_steps_min_seconds"] = self.steps_min.value()
        dd["between_steps_max_seconds"] = self.steps_max.value()
        dd["between_scripts_min_seconds"] = self.scripts_min.value()
        dd["between_scripts_max_seconds"] = self.scripts_max.value()
        cfg.setdefault("grok", {})["render_timeout_seconds"] = self.render_timeout.value()
        ar = cfg.setdefault("auto_resume", {})
        ar["enabled"] = self.auto_enabled.isChecked()
        ar["check_interval_minutes"] = self.auto_interval.value()
        return cfg

    def save(self) -> None:
        save_config(self.config_path, self.collect())
        self.accept()
