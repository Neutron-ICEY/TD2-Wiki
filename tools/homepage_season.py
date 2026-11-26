"""Refresh the homepage season calendar from the installed game export."""
import argparse
from datetime import datetime, timezone
import json
import re

from tools.equipment import native_tree
from tools.equipment.crafting import scalar
from tools.equipment.native import Native
from tools.generation import apply, plan
from tools.identity import ROOT, registry


SCHEDULE = "hunter/game system data/juice/scheduling/season_wrapper_schedule.mgameschedule"


def utc(value):
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def interval(period):
    start, last = native_tree.prop(period, "myActiveTime").strip('"').split(" to ")
    return utc(start), utc(last) + 1


def season_periods(native, wrapper_uids):
    schedule, = native_tree.parse(native.file(SCHEDULE).read_text("utf-8"))["children"]
    for period in native_tree.child(schedule, "myManualEntries")["children"]:
        entries = native_tree.child(period, "myEntries")
        for entry in entries["children"] if entries else ():
            if not entry["header"].startswith("GameScheduleEntrySeasonWrapper "):
                continue
            ref = native_tree.reference(native_tree.prop(entry, "mySeasonWrapper"))
            if ref["uid"] in wrapper_uids:
                yield period, ref, interval(period)


def sprite_ref(value):
    sheet = re.search(r'([^/"]+)\.spritesheet', value or "")
    sprite = re.search(r'mySpriteId = (-?\d+)', value or "")
    if not sheet or not sprite:
        raise ValueError(f"Invalid calendar sprite reference: {value}")
    return sheet[1], int(sprite[1])


def calendar_source(root, assets):
    native = Native(root / "resources/game/current/raw_files")
    by_uid = {row["native_season"]["wrapper_uid"]: row for row in assets if "native_season" in row}
    icons = {(row["native_sprite"]["sheet"], row["native_sprite"]["id"]): row["title"].split(":", 1)[1]
             for row in assets if "native_sprite" in row}
    seasons = []
    for _, ref, (start, end) in season_periods(native, by_uid):
        cover = by_uid[ref["uid"]]
        path = "hunter/game system data/juice/seasonwrapper/" + ref["name"] + ".mseasonwrapper"
        record = native.record(path, ref["uid"])
        textures = [p["raw_value"] for p in record["properties"] if p["field"] == "mySecondaryStoreTexture"]
        if textures != [cover["native_season"]["texture"]]:
            raise ValueError("The season no longer points to its registered artwork: " + path)
        code = re.fullmatch(r"seasonwrapper_(y\d+s\d+)", ref["name"], re.IGNORECASE)
        icon = sprite_ref(scalar(native, record, "mySeasonPassIcon"))
        if not code or icon not in icons:
            raise ValueError("Missing season code or unregistered season badge: " + path)
        seasons.append((start, end, code[1].upper(), native.text(record, "myShortDescription"),
                        cover["title"].split(":", 1)[1], icons[icon], ref["uid"]))
    if sorted(row[-1] for row in seasons) != sorted(by_uid):
        raise ValueError("Each registered cover must resolve to exactly one scheduled season")
    lines = ["return {"]
    previous_end = 0
    for start, end, title, name, image, icon, _ in sorted(seasons):
        if not previous_end <= start < end or not title or not name:
            raise ValueError("Invalid or overlapping season interval or missing localized name")
        previous_end = end
        fields = ", ".join(key + " = " + json.dumps(value, ensure_ascii=False) for key, value in
                           (("start", start), ("finish", end), ("title", title), ("name", name),
                            ("image", image), ("icon", icon)))
        lines.append("    { " + fields + " },")
    return "\n".join([*lines, "}", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write the registered generated module; default checks it")
    args = parser.parse_args()
    entries = registry(ROOT)
    by_id = {row["id"]: row for row in entries}
    row = by_id["td2-home-season-data"]
    source = row["source"]
    result = calendar_source(ROOT, [by_id[key] for key in row["asset_relationships"]])
    batch = plan(ROOT, {source: result}, {"entries": entries}, {source: "tools.homepage_season"})
    apply(batch, check=not args.write)


if __name__ == "__main__":
    main()
