"""Build the GitHub Pages site into _site/.

    uv run --group site python site/build.py && python3 -m http.server -d _site

The landing page is site/index.content.html; the other pages are rendered from the
Markdown docs, so the site and the repository docs never disagree.
"""

import re
import shutil
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT = ROOT / "_site"
REPO = "https://github.com/dntAtMe/screenwriter"

# (output file, nav label, title, source markdown or None for the landing page)
PAGES = [
    ("index.html", "Home", "Screenwriter", None),
    ("install.html", "Installing", "Installing", ROOT / "docs" / "installing.md"),
    ("guide.html", "User guide", "User guide", ROOT / "docs" / "user-guide.md"),
    ("changelog.html", "What's new", "What's new", ROOT / "CHANGELOG.md"),
]
LINKS = {  # links inside the Markdown → site URLs
    "installing.md": "install.html",
    "docs/installing.md": "install.html",
    "user-guide.md": "guide.html",
    "docs/user-guide.md": "guide.html",
    "../CHANGELOG.md": "changelog.html",
    "CHANGELOG.md": "changelog.html",
    "development.md": f"{REPO}/blob/main/docs/development.md",
    "docs/development.md": f"{REPO}/blob/main/docs/development.md",
    "LICENSE": f"{REPO}/blob/main/LICENSE",
}
DESCRIPTION = "A free writing app for screenplays, books, notes and ideas, for macOS, Windows and Linux."


def rewrite_links(html: str) -> str:
    def fix(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        path, _, anchor = url.partition("#")
        if path in LINKS:
            url = LINKS[path] + (f"#{anchor}" if anchor else "")
        elif path.startswith("docs/images/"):
            url = path.removeprefix("docs/")
        return f'{attr}="{url}"'

    return re.sub(r'(href|src)="([^"]+)"', fix, html)


def render(source: Path) -> tuple[str, str]:
    text = source.read_text(encoding="utf-8")
    text = re.sub(r"^\[[^\]]+\]: https?://\S+\n?", "", text, flags=re.MULTILINE)  # changelog link refs
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])
    html = md.convert(text)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", html)
    return rewrite_links(html), re.sub("<[^>]+>", "", title.group(1)) if title else ""


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    template = (SITE / "page.html").read_text(encoding="utf-8")
    for file, label, title, source in PAGES:
        nav = " ".join(
            f'<a href="{f}"{" aria-current=page" if f == file else ""}>{l}</a>'
            for f, l, _, _ in PAGES[1:]
        ) + f' <a href="{REPO}">GitHub</a>'
        if source is None:
            content, scripts = (SITE / "index.content.html").read_text(encoding="utf-8"), '<script src="download.js"></script>'
        else:
            body, _ = render(source)
            content, scripts = f'<article class="doc wrap narrow">\n{body}\n</article>', ""
        page = template.format(title=title, description=DESCRIPTION, nav=nav, content=content, scripts=scripts)
        (OUT / file).write_text(page, encoding="utf-8")
    shutil.copytree(ROOT / "docs" / "images", OUT / "images")
    shutil.copy(ROOT / "screenwriter" / "resources" / "icon.png", OUT / "icon.png")
    for asset in ("style.css", "download.js"):
        shutil.copy(SITE / asset, OUT / asset)
    (OUT / ".nojekyll").touch()
    print(f"built {len(PAGES)} pages into {OUT}")


if __name__ == "__main__":
    main()
