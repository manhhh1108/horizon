"""Application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Allow running as `python main.py` from inside horizon_tool/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from horizon_tool.core.config_loader import AppConfig  # noqa: E402
from horizon_tool.gui.main_window import MainWindow  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.yaml"


def main() -> int:
    app = QApplication(sys.argv)
    config = AppConfig.load(CONFIG_PATH)
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
