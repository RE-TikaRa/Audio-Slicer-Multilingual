import os
import sys
import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QFont

import qdarktheme

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from audio_slicer.gui import mainwindow

if __name__ == '__main__':
    # Write console outputs to log file.
    __stderr__ = sys.stderr
    date_time = datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    folder = os.path.exists('log')
    if not folder: 
        os.makedirs('log')
    sys.stderr = open(f'log/log {date_time}.txt', 'w')
    
    app = QApplication(sys.argv)
    app.setApplicationName("Audio Slicer")
    app.setApplicationDisplayName("Audio Slicer")

    # Apply auto dark theme
    qdarktheme.setup_theme(
        theme="auto",
        # custom_colors={
        #     "[dark]": {
        #         "primary": "#8dc8d1",
        #         },
        #     "[light]": {
        #         "primary": "#3b7d92",
        #     }
        # }
    )

    # Auto dark title bar on Windows 10/11
    style = QStyleFactory.create("fusion")
    app.setStyle(style)

    font = QFont('Microsoft YaHei UI')
    font.setPixelSize(12)
    app.setFont(font)

    window = mainwindow.MainWindow()
    window.show()

    sys.exit(app.exec())
