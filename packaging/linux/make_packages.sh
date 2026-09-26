#!/usr/bin/env bash
# Package dist/Screenwriter as a .tar.gz and an AppImage.
#   packaging/linux/make_packages.sh 0.1.0 out/
set -euo pipefail
VERSION=$1 OUT=$2
NAME="Screenwriter-$VERSION-linux-x86_64"
mkdir -p "$OUT" build

# icons
python3 - <<'PY'
from PIL import Image
icon = Image.open("screenwriter/resources/icon.png")
icon.resize((256, 256), Image.LANCZOS).save("build/screenwriter.png")
PY

# plain archive: the app folder plus a desktop entry and icon
rm -rf "build/$NAME" && mkdir -p "build/$NAME"
cp -R dist/Screenwriter/. "build/$NAME/"
cp packaging/linux/screenwriter.desktop build/screenwriter.png "build/$NAME/"
tar -C build -czf "$OUT/$NAME.tar.gz" "$NAME"

# AppImage
APPDIR=build/AppDir
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -R dist/Screenwriter/. "$APPDIR/usr/bin/"
cp packaging/linux/screenwriter.desktop "$APPDIR/"
cp packaging/linux/screenwriter.desktop "$APPDIR/usr/share/applications/"
cp build/screenwriter.png "$APPDIR/screenwriter.png"
cp build/screenwriter.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/Screenwriter" "$@"
SH
chmod +x "$APPDIR/AppRun"
if [ ! -x build/appimagetool ]; then
  curl -fsSL -o build/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x build/appimagetool
fi
ARCH=x86_64 build/appimagetool --appimage-extract-and-run "$APPDIR" "$OUT/$NAME.AppImage"
