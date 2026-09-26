# Installing Screenwriter

Download the file for your system from the [latest release](https://github.com/dntAtMe/screenwriter/releases/latest).
Each release also lists `SHA256SUMS.txt` if you want to verify a download.

Screenwriter isn't code-signed yet (signing certificates cost money for a hobby project), so macOS and
Windows show a warning the first time you open it. The steps below get past that once; after that the
app opens normally.

## macOS

1. Download `Screenwriter-<version>-macos-arm64.dmg` (Apple Silicon: M1 and later).
   Intel Macs use `…-macos-intel.dmg` when a release has one.
2. Open the `.dmg` and drag **Screenwriter** onto **Applications**.
3. Open Screenwriter from Applications. macOS says it *can't verify* the app — click **Done** (not *Move to Bin*).
4. Open **System Settings → Privacy & Security**, scroll down to *“Screenwriter” was blocked…* and click **Open Anyway**, then confirm.

If you prefer the terminal, this does the same as step 4:

```bash
xattr -dr com.apple.quarantine /Applications/Screenwriter.app
```

Requires macOS 12 or later.

## Windows

1. Download `Screenwriter-<version>-windows-x64-setup.exe`.
2. Run it. If **Windows protected your PC** appears, click **More info → Run anyway**.
3. Follow the installer. It installs for your user account only and doesn't need administrator rights;
   it adds Screenwriter to the Start menu (and, if you tick the box, the desktop).

No installer wanted? Download `…-windows-x64-portable.zip`, unzip it anywhere and run `Screenwriter.exe`.

To uninstall, use **Settings → Apps → Installed apps → Screenwriter**.

## Linux

**AppImage** (works on most distributions):

```bash
chmod +x Screenwriter-*-linux-x86_64.AppImage
./Screenwriter-*-linux-x86_64.AppImage
```

If it complains about FUSE, install `libfuse2` (Ubuntu/Debian: `sudo apt install libfuse2`), or run it with
`--appimage-extract-and-run`.

**Archive**: unpack `…-linux-x86_64.tar.gz` and run `Screenwriter` inside the folder. The folder also contains
`screenwriter.desktop` and `screenwriter.png` if you want a menu entry — copy them to
`~/.local/share/applications/` and `~/.local/share/icons/`, and point `Exec=` at the full path of `Screenwriter`.

Built on Ubuntu 22.04; any x86-64 distribution from about 2022 onwards should work.

## Your projects and settings

- Projects are ordinary folders wherever you save them — uninstalling the app never touches them.
- Settings (window layout, recent projects) live in the usual place for your system: `~/Library/Preferences`
  on macOS, the registry on Windows, `~/.config` on Linux.

## Updating

Download and install the new version over the old one. Your projects and settings stay as they are.
