#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --onedir --name syswatch \
  --distpath "$PWD/dist" --workpath "$PWD/build" --specpath "$PWD/build" \
  --hidden-import PySide6.QtDBus \
  --add-data "$PWD/plasma-wallpaper:plasma-wallpaper" \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick \
  --exclude-module pytest main.py
cp README.md dist/syswatch/README.md
getconf GNU_LIBC_VERSION > dist/syswatch/BUILD-INFO.txt
uname -m >> dist/syswatch/BUILD-INFO.txt
install -m 755 packaging/install.sh dist/syswatch/install.sh
tar -C dist -czf "dist/syswatch-linux-$(uname -m).tar.gz" syswatch
printf 'Package ready: %s/dist/syswatch-linux-%s.tar.gz\n' "$PWD" "$(uname -m)"
