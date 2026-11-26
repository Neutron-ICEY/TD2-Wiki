"""Generate the homepage activity calendar from the exported game schedules."""
import argparse
import json

from tools.equipment import native_tree as tree
from tools.equipment.crafting import scalar
from tools.equipment.native import Native
from tools.generation import apply, plan
from tools.homepage_season import SCHEDULE, interval, season_periods, sprite_ref
from tools.identity import ROOT, registry

JUICE = "hunter/game system data/juice/"
SCHEDULING = JUICE + "scheduling/"
# The type labels are the localization GUIDs of the in-game calendar.
EVENT_TYPES = {
    "GameScheduleEntrySeasonWrapperGenericEvent": ("mySeasonWrapperGenericEvent", "seasonwrapper/seasonwrappergenericevents.juice",
        "mySeasonWrapperPosterTextureString", "mySeasonWrapperIconString", "81EF474E66A77DB60006B5B0B9CBCCAE"),
    "GameScheduleEntryGlobalEvent": ("myGlobalEvent", "globalevents/globalevents.juice",
        "mySeasonWrapperPosterTextureString", "myIconString", "81EF474E66A77DB60006B5B1FF9297C4"),
    "GameScheduleEntrySeasonWrapperAnnouncement": ("mySeasonWrapperAnnouncement", "seasonwrapper/seasonwrapperannouncements.juice",
        "myBackgroundTexture", "myIconSprite", "1B4546E267C707B4000BF2BE13DC23A4"),
}


def schedule_file(native, ref, extension):
    path = SCHEDULING + ref["name"].lower() + extension
    nodes = tree.parse(native.file(path).read_text("utf-8"))["children"]
    node, = (n for n in nodes if n["header"].endswith("uid=" + ref["uid"] + " >"))
    return node


def season_events(native, period, start, end, enabled):
    for group in tree.child(period, "myOffsetManualEntries")["children"]:
        if tree.prop(group, "myGameSchedule") not in enabled:
            continue
        for entry in tree.child(group, "myEntries")["children"]:
            spec = EVENT_TYPES.get(entry["header"].split()[0])
            if not spec:
                continue
            field, path, poster, icon, label = spec
            ref = tree.reference(tree.prop(entry, field))
            record = native.record(JUICE + path, ref["uid"])
            texture = scalar(native, record, poster)
            if tree.prop(group, "myTimeUnit") != "Days":
                raise ValueError("Unexpected calendar time unit: " + group["header"])
            offset, duration = (int(tree.prop(group, key)) for key in ("myOffset", "myDuration"))
            begin = start + offset * 86400
            finish = end if duration == -1 else min(end, begin + duration * 86400)
            if not start <= begin < finish:
                raise ValueError("Invalid activity interval: " + group["header"])
            yield (begin, finish, native.text(record, "myTitle"), texture,
                   native.localization("zh")[label], sprite_ref(scalar(native, record, icon)))


def project_background(native, project, slot_type):
    override = scalar(native, project, "myBackgroundImageOverride")
    if override and override != '""':
        return override
    slots = native.document(JUICE + "projects/projectslots.juice")["resources"]
    slot_uid, = (row["resource_uid"] for row in slots if scalar(native, row, "mySlotType") == slot_type)
    sources = native.document(JUICE + "projects/projectsources.juice")
    index, = (link["source_index"] for link in sources["links"]
              if link["field"] == "ProjectSlot" and link["target_uid"] == slot_uid)
    return scalar(native, sources["resources"][index], "myBackgroundImage")


def project_events(native, slot, windows):
    schedule = schedule_file(native, tree.reference(tree.prop(slot, "mySchedule")), ".mgameschedule")
    slot_type = slot["header"].removeprefix("my").removesuffix("Schedule")
    for period in tree.child(schedule, "myPeriods")["children"]:
        start, end = interval(period)
        if not any(a < end and start < b for a, b in windows):
            continue
        settings = tree.child(period, "myPoolSettings")
        ref = tree.reference(tree.prop(settings, "myPool"))
        pool = schedule_file(native, ref, ".mgameschedulepool")
        # An ordered project chain is a single event; its first entry carries the event heading.
        if tree.prop(settings, "myPoolSelectionMethod") != "OrderedFromStart":
            raise ValueError("Unsupported event project pool: " + ref["name"])
        first = tree.child(pool, "myEntries")["children"][0]
        project = tree.reference(tree.prop(first, "myProject"))
        record = native.record(JUICE + "projects/projects.juice", project["uid"])
        yield (start, end, native.text(record, "myProjectSourceNameOverride"), project_background(native, record, slot_type),
               native.localization("zh")["F3127A025BF3E918001A7602B334A83E"], sprite_ref(scalar(native, record, "myProjectIconOverride")))


def calendar_source(root, entries):
    by_id = {row["id"]: row for row in entries}
    assets = [by_id[key] for key in by_id["td2-home-event-data"]["asset_relationships"]]
    by_texture = {row["native_event"]["texture"]: row["title"].split(":", 1)[1] for row in assets if "native_event" in row}
    by_sprite = {(row["native_sprite"]["sheet"], row["native_sprite"]["id"]): row["title"].split(":", 1)[1]
                 for row in assets if "native_sprite" in row}
    native = Native(root / "resources/game/current/raw_files")
    active, = tree.parse(native.file(SCHEDULING + "activegameschedules.juice").read_text("utf-8"))["children"]
    slots = [slot for slot in active["children"] if tree.prop(slot, "myIsEnabled", "TRUE") == "TRUE"
             and tree.prop(slot, "mySchedule")]
    enabled = {tree.reference(tree.prop(slot, "mySchedule"))["uid"] for slot in slots}
    wrapper = tree.reference(tree.prop(tree.child(active, "mySeasonWrapperSchedule"), "mySchedule"))
    if SCHEDULING + wrapper["name"] + ".mgameschedule" != SCHEDULE or wrapper["uid"] not in enabled:
        raise ValueError("The active season calendar changed")
    season_art = (by_id[k] for k in by_id["td2-home-season-data"]["asset_relationships"])
    seasons = {row["native_season"]["wrapper_uid"] for row in season_art if "native_season" in row}
    events, windows = [], []
    for period, _, (start, end) in season_periods(native, seasons):
        windows.append((start, end))
        events.extend(season_events(native, period, start, end, enabled))
    for slot in slots:
        if slot["header"].startswith("myCustomEvent") and slot["header"].endswith("Schedule"):
            events.extend(project_events(native, slot, windows))
    lines = ["return {"]
    for start, end, name, texture, kind, sprite in sorted(set(events)):
        if not name or texture not in by_texture or sprite not in by_sprite:
            raise ValueError(f"Unregistered calendar artwork or missing Chinese name: {name!r} {texture} {sprite}")
        fields = {"start": start, "finish": end, "name": name, "kind": kind, "image": by_texture[texture], "icon": by_sprite[sprite]}
        lines.append("    { " + ", ".join(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in fields.items()) + " },")
    return "\n".join([*lines, "}", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    entries = registry(ROOT)
    row, = (r for r in entries if r["id"] == "td2-home-event-data")
    source = row["source"]
    batch = plan(ROOT, {source: calendar_source(ROOT, entries)}, {"entries": entries}, {source: "tools.homepage_events"})
    apply(batch, check=not args.write)


if __name__ == "__main__":
    main()
