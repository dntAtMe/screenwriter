#!/usr/bin/env bash
# Wrap dist/Screenwriter.app in a drag-to-Applications disk image.
#   packaging/macos/make_dmg.sh 0.1.0 arm64 out/
set -euo pipefail
VERSION=$1 ARCH=$2 OUT=$3
STAGE=build/dmg
rm -rf "$STAGE" && mkdir -p "$STAGE" "$OUT"
cp -R dist/Screenwriter.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Screenwriter $VERSION" -srcfolder "$STAGE" -ov -format UDZO \
  "$OUT/Screenwriter-$VERSION-macos-$ARCH.dmg"
