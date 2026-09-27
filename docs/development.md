# Development

Screenwriter is Python 3.13 + Qt 6 via [PySide6](https://doc.qt.io/qtforpython-6/), managed with
[uv](https://docs.astral.sh/uv/).

```bash
uv run python -m screenwriter                     # run from source (reopens the last project)
uv run python -m screenwriter path/to/project     # open a specific project
uv run pytest                                     # tests (headless: QT_QPA_PLATFORM=offscreen)
```

Try things on a **copy** of the sample project — the app autosaves into whatever it opens:

```bash
cp -R "examples/The Lighthouse" /tmp/ && uv run python -m screenwriter "/tmp/The Lighthouse"
```

## Layout

| Path | What |
|---|---|
| `screenwriter/app.py` | entry point, smoke-test hooks for packaged builds |
| `screenwriter/mainwindow.py` | window, menus, tabs, autosave; wires everything together |
| `screenwriter/panes.py` | the tab area: one tab pane or a split of two, behind a QTabWidget-like interface |
| `screenwriter/formatbar.py`, `shortcuthints.py`, `quickopen.py` | formatting toolbar, Ctrl/Alt shortcut hints, Go to Document (double Shift) |
| `screenwriter/project.py` | on-disk project format (`project.json` + `docs/`) |
| `screenwriter/binder.py` | the binder tree |
| `screenwriter/editors/` | prose, screenplay, board and story-bible editors |
| `screenwriter/fountain.py` | Fountain parsing (Qt-free) |
| `screenwriter/bible.py`, `board.py`, `snapshots.py` | story bible, boards, snapshots (Qt-free models) |
| `screenwriter/projecthistory.py` | project history: save points in `.history/` (git objects via dulwich) |
| `screenwriter/sync.py`, `merge.py` | cloud-folder sync: `.screenwriter` package files, presence lock; paragraph and card merging, `conflicts.json` |
| `screenwriter/google_drive.py`, `synctargets.py` | Sign in with Google (OAuth + PKCE) and Drive as a sync target — see [Google Drive setup](google-drive-setup.md) |
| `screenwriter/export/` | screenplay PDF/FDX and manuscript PDF/Word/Markdown |
| `screenwriter/resources/icon.png` | app icon — regenerate with `uv run python packaging/make_icon.py` |
| `packaging/` | PyInstaller spec and per-platform installer scripts |
| `.github/workflows/` | CI (tests on push) and Release (builds and publishes) |

Every editor offers the same small interface to the main window (`text`, `set_text`, `is_modified`,
`mark_saved`, `stats`, `outline`, `search_text`, `reveal`, `jump_to_line`, …) — see `editors/common.py`.

## Building the app locally

```bash
uv sync --group build
uv run pyinstaller packaging/screenwriter.spec --noconfirm   # → dist/Screenwriter(.app)
packaging/macos/make_dmg.sh 0.3.1 arm64 out                   # macOS disk image
uv run bash packaging/linux/make_packages.sh 0.3.1 out        # Linux .tar.gz + .AppImage
```

Windows installers are built with [Inno Setup](https://jrsoftware.org/isinfo.php) from
`packaging/windows/installer.iss` (see the Release workflow for the exact command).

Check a build starts and can export everything, without clicking:

```bash
SCREENWRITER_SMOKE_TEST=1 SCREENWRITER_SMOKE_EXPORT=/tmp/smoke \
  dist/Screenwriter.app/Contents/MacOS/Screenwriter "/tmp/The Lighthouse"
```

## Releasing

Versions follow [semantic versioning](https://semver.org): `MAJOR.MINOR.PATCH`, with a `-beta.1`-style
suffix for pre-releases (published as GitHub pre-releases).

1. Move the changes from **Unreleased** in [`CHANGELOG.md`](../CHANGELOG.md) under a new `## [x.y.z] - YYYY-MM-DD` heading.
2. Set the version in **both** `screenwriter/__init__.py` (`__version__`) and `pyproject.toml` (`version`),
   then `uv lock`.
3. Check: `python3 packaging/release.py check vx.y.z` — it fails if the versions or the changelog section don't match.
4. Commit, then tag and push:

   ```bash
   git tag -a vx.y.z -m "Screenwriter x.y.z"
   git push origin main vx.y.z
   ```

The **Release** workflow then runs the tests on each platform, builds and smoke-tests the app, packages it
(`.dmg`, `-setup.exe`, portable `.zip`, `.AppImage`, `.tar.gz`) and publishes a GitHub Release with the
changelog section as its notes and a `SHA256SUMS.txt`.

To test the packaging without publishing, run the workflow by hand: **Actions → Release → Run workflow**.
The builds are attached to the run as artifacts.

If a release build fails, fix it on `main`, then move the tag: `git tag -fa vx.y.z … && git push -f origin vx.y.z`
(only before anyone has downloaded it — otherwise make a new patch release).

## Website

The project site at <https://dntatme.github.io/screenwriter/> is built from `site/` (landing page, styles,
download script) plus the Markdown in `docs/` and `CHANGELOG.md`, by the **Website** workflow on every push to
`main` that touches them. Its download buttons read the latest GitHub Release, so a new release shows up there
without rebuilding the site. Preview locally:

```bash
uv run --group site python site/build.py && python3 -m http.server -d _site
```

## Not done yet

- **Code signing / notarisation** (macOS Developer ID, Windows Authenticode) — until then users see the
  first-launch warnings described in [Installing](installing.md).
- **Intel macOS** builds depend on GitHub's Intel runners (`macos-15-intel`); that job is allowed to fail.
