"""QApplication setup and main window initialization."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from src.comic_file import cbr_support_available
from src.main_window import MainWindow

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon.png"


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CBRRanger")
    if ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    window = MainWindow()
    window.show()

    if not cbr_support_available():
        QMessageBox.warning(
            window,
            "CBR support unavailable",
            "Opening CBR (RAR) files requires the 'unrar' or 'unar' tool, "
            "which was not found on this system.\n\n"
            "CBZ files are unaffected. Install unrar (e.g. 'sudo pacman -S unrar' "
            "on Arch, 'sudo apt install unrar' on Debian/Ubuntu) to enable CBR support.",
        )

    args = app.arguments()
    if len(args) > 1:
        window.load_comic(args[1])

    return app.exec()
