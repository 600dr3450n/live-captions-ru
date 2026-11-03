"""Скриншоты нового окна настроек (три раздела) и предпросмотра субтитров."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QListWidget

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "app"))

import paths  # noqa: E402
import settings as settings_module  # noqa: E402
from overlay import SubtitleOverlay  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

ART = PROJECT / "_artifacts"
ART.mkdir(exist_ok=True)


def main() -> int:
    app = QApplication(sys.argv)
    settings = settings_module.Settings()

    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_preview(True)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    overlay.grab().toImage().save(str(ART / "v5_preview.png"))
    print("предпросмотр:", ART / "v5_preview.png")
    overlay.set_preview(False)
    overlay.hide()

    dialog = SettingsDialog(
        settings,
        on_change=lambda s: None,
        on_apply=lambda s: None,
        on_edit_box=lambda: None,
    )
    dialog.resize(780, 640)
    dialog.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    nav = dialog.findChild(QListWidget)
    titles = [nav.item(index).text() for index in range(nav.count())]
    print("разделы:", titles)
    for index, title in enumerate(titles):
        nav.setCurrentRow(index)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.02)
        name = {0: "general", 1: "appearance", 2: "about"}.get(index, str(index))
        dialog.grab().save(str(ART / f"v5_dialog_{name}.png"))
        print(f"  скриншот: v5_dialog_{name}.png ({title})")
    dialog.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
