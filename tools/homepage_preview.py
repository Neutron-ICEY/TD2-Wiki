"""Render the homepage and both destination indexes from their registered Wiki sources."""
import argparse
from datetime import datetime, time, timedelta, timezone
from html import escape
import json
from pathlib import Path
import re
import shutil

from tools.equipment.preview import render
from tools.identity import ROOT, registry
from tools.publish.asset_dependencies import AssetDependencies


PAGES = {"td2-home": "index.html", "equipment-index": "equipment.html", "weapon-index": "weapons.html"}
HUD_NUMERALS = ROOT / "resources/game/current/raw_files/rogue/baked/fonts/preset fonts/borda/borda-medium.otf"
MEDIA = {
    "skin.css": "tools/equipment/preview-skin.css",
    "common.css": "wiki/pages/site/Common.css",
    "reader.css": "ui/brand-sets/brand-sets.css",
    "reader.js": "ui/brand-sets/brand-sets.js",
}

def huiji_snapshot(raw, snapshot):
    """Substitute captured Huiji output for services unavailable in the offline preview."""
    for word, count in snapshot["magicWords"].items():
        raw = raw.replace("{{" + word + "}}", str(count))
    raw = raw.replace("<commentsoftheday />", snapshot["latestComments"]["html"])

    def activity(match):
        rows = snapshot["activityRows"][:int(match[1])]
        return '<div class="activityembed-wrapper">' + "".join(rows) + '</div>'

    return re.sub(r'<siteactivity style="log" limit="(\d+)"\s*/>', activity, raw)


def build(output, skin_snapshot=None, as_of=None, *, without_assets=False):
    if without_assets:
        snapshot = {
            "magicWords": dict.fromkeys(("NUMBEROFARTICLES:R", "NUMBEROFEDITS:R", "NUMBEROFFOLLOWERS"), "—"),
            "latestComments": {"html": ""}, "activityRows": [],
        }
    else:
        snapshot = json.loads(Path(__file__).with_name("homepage-preview-snapshot.json").read_text("utf-8"))
    preview_date = datetime.now(timezone.utc)
    if as_of is not None:
        instant = as_of if isinstance(as_of, datetime) else datetime.combine(as_of, time())
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone(timedelta(hours=8)))
        preview_date = instant.astimezone(timezone.utc)
    entries = registry(ROOT)
    by_id = {row["id"]: row for row in entries}
    page_urls = {by_id[key]["title"]: name for key, name in PAGES.items()}

    def source(row):
        return (ROOT / row["source"]).read_text(encoding="utf-8")

    deps = AssetDependencies(entries, source)
    icons = set()
    for key in ("td2-home", "td2-home-season-data", "td2-home-event-data", "td2-home-statistics",
                "td2-home-navigation", "equipment-navbox", "weapon-navigation"):
        icons.update(deps.resolve(by_id[key]))

    styles = source(by_id["td2-home-style"]).strip()
    if not (styles.startswith("<style>") and styles.endswith("</style>")):
        raise ValueError("Expected the homepage Html stylesheet")
    output.mkdir(parents=True, exist_ok=False)
    images = output / "images"
    images.mkdir()
    if not without_assets:
        shutil.copy(Path(__file__).with_name("homepage-preview-avatar.png"), images)
        for key in icons:
            row = by_id[key]
            shutil.copyfile(ROOT / row["source"], images / row["title"].split(":", 1)[1])
    local_numerals = ""
    if not without_assets and HUD_NUMERALS.is_file():
        shutil.copyfile(HUD_NUMERALS, images / HUD_NUMERALS.name)
        local_numerals = ('<style>@font-face{font-family:"Borda Medium";src:local("Borda Medium"),'
                          'url("images/borda-medium.otf") format("opentype");unicode-range:U+0030-0039}</style>')
    for name, relative in MEDIA.items():
        shutil.copyfile(ROOT / relative, output / name)
    if skin_snapshot is not None:
        sheets = {"media/wiki-background.png": "reader.css", "media/Sansation_Regular.ttf": "common.css"}
        manifest = json.loads((skin_snapshot / "manifest.json").read_text(encoding="utf-8"))
        for asset in manifest["files"]:
            if asset["file"] in sheets:
                original = skin_snapshot / asset["file"]
                css = output / sheets[asset["file"]]
                local = shutil.copyfile(original, images / original.name)
                css.write_text(css.read_text(encoding="utf-8").replace(asset["url"], local.relative_to(output).as_posix()),
                               encoding="utf-8")
    (output / "home.css").write_text(styles.removeprefix("<style>").removesuffix("</style>").strip() + "\n", encoding="utf-8")

    for key, name in [*PAGES.items(), ("td2-home", "empty.html")]:
        row = by_id[key]
        raw = re.sub(r"__(?:NOTITLE|NOTOC|NOEDITSECTION|NOCOMMENT|NOREC)__", "", source(row))
        style_link = ""
        heading = ""
        script = ""
        if key == "td2-home":
            call = "{{#html:" + by_id["td2-home-style"]["title"].split(":", 1)[1] + "|{} }}"
            if raw.count(call) != 1:
                raise ValueError("Homepage must include its own Html stylesheet once")
            raw = huiji_snapshot(raw.replace(call, ""), snapshot)
            if name == "empty.html":
                raw = raw.replace("{{TD2首页消息栏}}", "{{TD2首页消息栏|赛季=|活动=}}", 1)
            style_link = '<link rel="stylesheet" href="home.css">' + local_numerals
            script = '<script src="reader.js"></script>'
            if as_of:
                epoch = int(preview_date.timestamp() * 1000)
                script = f'<script>Date.now = () => {epoch} + Math.floor(performance.now());</script>' + script
        else:
            heading = "<h1>" + escape(row["title"]) + "</h1>"
            script = '<script src="reader.js"></script>'
        body = render(raw, output, page_urls, today=preview_date).replace('src="/images/', 'src="images/')

        def bullet_list(match):
            return "<ul>" + "".join("<li>" + line[2:] + "</li>" for line in match[0].splitlines()) + "</ul>\n"

        body = re.sub(r"^(?:\* [^\n]*(?:\n|$))+", bullet_list, body, flags=re.M)
        tab_title = "全境封锁2" if key == "td2-home" else escape(row["title"]) + " · 全境封锁2"
        shell = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{tab_title}</title>
<link rel="stylesheet" href="skin.css"><link rel="stylesheet" href="common.css"><link rel="stylesheet" href="reader.css">
<style>
body {{ margin: 0; min-height: 100vh; color: #f5f5f5; line-height: 1.5; }}
main {{ max-width: 74rem; margin: 0 auto; padding: clamp(.8rem, 3vw, 2.5rem); }}
</style>{style_link}</head>
<body class="ns-0 ns-subject action-view sitedir-ltr"><main id="wiki-body"><div id="content">{heading}
<div id="mw-content-text" class="mw-content-ltr"><div class="mw-parser-output">{body}</div></div>
</div></main>{script}</body></html>
"""
        (output / name).write_text(shell, encoding="utf-8")
        if name == "index.html":
            (output / "release.html").write_text(shell.replace(local_numerals, "", 1), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Fresh static preview directory")
    parser.add_argument("--skin-snapshot", type=Path, help="Huiji backup with manifest.json and original skin media")
    parser.add_argument("--as-of", type=datetime.fromisoformat, help="Replay at an ISO date/time; absent timezone means Beijing time")
    parser.add_argument("--without-assets", action="store_true", help="Preview without local images or a captured site activity sample")
    args = parser.parse_args()
    build(args.output, args.skin_snapshot, args.as_of, without_assets=args.without_assets)
