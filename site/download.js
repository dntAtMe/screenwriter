// Point download links at the files of the latest GitHub release, and pick the
// right one for this computer. Without JavaScript the links go to the releases page.
(async () => {
  const REPO = "dntAtMe/screenwriter";
  let release;
  try {
    const response = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`);
    if (!response.ok) return;
    release = await response.json();
  } catch {
    return;
  }
  const asset = (suffix) => release.assets.find((a) => a.name.endsWith(suffix));
  const size = (a) => `${Math.round(a.size / 1048576)} MB`;

  for (const link of document.querySelectorAll("[data-asset]")) {
    const a = asset(link.dataset.asset);
    if (a) {
      link.href = a.browser_download_url;
      link.title = `${a.name} (${size(a)})`;
    } else {
      link.closest("tr")?.querySelectorAll("td")[1] && (link.textContent += " (not in this release)");
    }
  }
  const version = release.tag_name.replace(/^v/, "");
  const note = document.getElementById("download-version");
  if (note) note.innerHTML = `Version <strong>${version}</strong> · <a href="${release.html_url}">release notes</a>`;

  const ua = navigator.userAgent;
  const platform = (navigator.userAgentData?.platform || navigator.platform || "").toLowerCase();
  let pick = null;
  if (platform.includes("mac") || /Mac OS X/.test(ua)) pick = ["macos-arm64.dmg", "macOS", "Apple Silicon · for Intel Macs see all downloads"];
  else if (platform.includes("win") || /Windows/.test(ua)) pick = ["windows-x64-setup.exe", "Windows", "Windows 10 and 11"];
  else if (platform.includes("linux") || /Linux/.test(ua)) pick = ["linux-x86_64.AppImage", "Linux", "AppImage for x86-64"];
  const button = document.getElementById("primary-download");
  const chosen = pick && asset(pick[0]);
  if (button && chosen) {
    button.href = chosen.browser_download_url;
    document.getElementById("primary-label").textContent = `Download for ${pick[1]}`;
    document.getElementById("primary-detail").textContent = `${version} · ${pick[2]} · ${size(chosen)}`;
  }
})();
