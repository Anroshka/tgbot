#!/usr/bin/env python3
"""Резервная копия бота в одну директорию: backups/backup_YYYYMMDD_HHMMSS/

Запуск из корня проекта:
  python3 scripts/backup_bot.py

Или из любой папки:
  python3 /путь/к/Tgbot/scripts/backup_bot.py

Скрипт копирует исходники, requirements, vpn_legal; при наличии — bot.db и .env.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUPS_DIR = ROOT / "backups"

ALWAYS_COPY = [
    "main.py",
    "db.py",
    "panel_api.py",
    "vpn_legal.py",
    "requirements.txt",
    "README.md",
    ".env.example",
]

OPTIONAL_COPY = [".env", "bot.db"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Бэкап Tgbot в backups/…")
    parser.add_argument(
        "--zip",
        action="store_true",
        help="После копирования собрать один архив backups/backup_….zip и удалить папку",
    )
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = BACKUPS_DIR / f"backup_{stamp}"
    dest.mkdir(parents=True, exist_ok=False)

    lines = [
        f"Создано (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Корень проекта: {ROOT}",
        "",
        "Файлы:",
    ]

    for name in ALWAYS_COPY:
        src = ROOT / name
        if not src.is_file():
            print(f"Пропуск (нет файла): {name}", file=sys.stderr)
            continue
        shutil.copy2(src, dest / name)
        lines.append(f"  + {name}")

    for name in OPTIONAL_COPY:
        src = ROOT / name
        if not src.is_file():
            lines.append(f"  (нет) {name}")
            continue
        shutil.copy2(src, dest / name)
        lines.append(f"  + {name}")

    (dest / "BACKUP_MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Готово: {dest}")

    if args.zip:
        archive_base = BACKUPS_DIR / f"backup_{stamp}"
        shutil.make_archive(str(archive_base), "zip", root_dir=dest.parent, base_dir=dest.name)
        shutil.rmtree(dest)
        print(f"Архив: {archive_base.with_suffix('.zip')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
