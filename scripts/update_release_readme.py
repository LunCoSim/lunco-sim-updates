"""Refresh the nightly installer table from paginated GitHub release data."""

import json
import sys
from pathlib import Path
from urllib.parse import quote


RELEASES_URL = "https://github.com/LunCoSim/lunco-sim-updates/releases"
INSTALLERS = (
    ("Windows x86-64", "LunCoSim-Windows-x86_64.msi"),
    ("macOS Apple Silicon", "LunCoSim-macOS-Apple-Silicon.pkg"),
    ("macOS Intel", "LunCoSim-macOS-Intel.pkg"),
    ("Linux x86-64", "LunCoSim-Linux-x86_64.AppImage"),
)
START = "<!-- nightly-downloads:start -->"
END = "<!-- nightly-downloads:end -->"


def render_downloads(pages):
    required_assets = {filename for _, filename in INSTALLERS}
    nightlies = [
        release
        for page in pages
        for release in page
        if not release["draft"]
        and release["tag_name"].startswith("nightly-")
        and release["published_at"]
        and required_assets.issubset(
            asset["name"] for asset in release["assets"] if asset["state"] == "uploaded"
        )
    ]
    nightlies.sort(key=lambda release: release["published_at"], reverse=True)
    if not nightlies:
        return "No nightly installers are currently available."

    header = ["Published (UTC)", *(platform for platform, _ in INSTALLERS)]
    rows = [header, ["---"] * len(header)]
    for release in nightlies[:2]:
        tag = quote(release["tag_name"], safe="")
        date = release["published_at"][:10]
        downloads = [
            f"[Download]({RELEASES_URL}/download/{tag}/{filename})"
            for _, filename in INSTALLERS
        ]
        rows.append([f"[{date}]({RELEASES_URL}/tag/{tag})", *downloads])
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def main():
    readme = Path(__file__).resolve().parents[1] / "README.md"
    contents = readme.read_text(encoding="utf-8")
    before, start, section = contents.partition(START)
    _, end, after = section.partition(END)
    if not (start and end) or contents.count(START) != 1 or contents.count(END) != 1:
        raise SystemExit("README must contain one nightly download section.")

    downloads = render_downloads(json.load(sys.stdin))
    updated = f"{before}{START}\n\n{downloads}\n\n{END}{after}"
    if updated != contents:
        readme.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
