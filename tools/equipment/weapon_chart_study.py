"""Rebuild the game chart catalog from versioned research observations."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .weapon_spread import NEMESIS, cone_angles

ROOT = Path(__file__).resolve().parents[2]
STUDY = Path('evidence/research/weapon-charts-26413016')
CATALOG = Path('data/equipment/weapon-charts.json')
SIGNATURE_RECOIL_UID = "028db20a5ca4b93c000352e84077d974"  # 迷你炮机枪
SIGNATURE_CHART_UIDS = frozenset({
    SIGNATURE_RECOIL_UID,
    "5d4179f15ad5f40900006e66c5e6ec16",  # TAC-50 C 步枪
})


def rebuild(root):
    directory = root / STUDY
    metadata = json.loads((directory / "control-manifest.json").read_bytes())
    metadata.pop("adsWalk")  # Native gait reference, separate from the Wiki comparison input.
    raw = (directory / "control-observations.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata.pop("sha256"):
        raise ValueError("Control observation archive checksum mismatch")
    mapping = json.loads((root / "data/equipment/native-map.json").read_bytes())
    registered = {row["uid"].lower(): row for family in mapping["weapons"] for row in family["items"]}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if sorted(archive.namelist()) != ["models.json", "traces.json"]:
            raise ValueError("Unexpected control archive members")
        observations = json.loads(archive.read("models.json"))
        traces = json.loads(archive.read("traces.json"))
    unreleased = {uid.lower() for uid in mapping.get("unreleased_items", {})}
    groups = {uid: row["group"] for uid, row in registered.items()}
    if groups != {uid: item["group"] for uid, item in observations.items() if uid not in unreleased}:
        raise ValueError("Registry and observed model groups differ")
    models = {}
    excluded_traces = set()
    for uid, item in observations.items():
        if uid in unreleased or (registered[uid]["kind"] == "signature" and uid not in SIGNATURE_CHART_UIDS):
            if "trace" in item:
                excluded_traces.add(item["trace"])
            continue
        model = {"group": groups[uid]}
        if uid == NEMESIS and item.keys() != model.keys():
            raise ValueError("Nemesis observations must contain only its group")
        if "modes" in item:
            model["angles"] = cone_angles(item["values"], model["group"], item["bonuses"],
                                         item["modes"], metadata["movementSpeed"])
        if "trace" in item:
            if registered[uid]["kind"] == "signature" and uid != SIGNATURE_RECOIL_UID:
                excluded_traces.add(item["trace"])
            else:
                model["trace"] = item["trace"]
        if len(model) > 1:
            models[uid] = model
    remaining_traces = {m["trace"] for m in models.values() if "trace" in m}
    for key in excluded_traces - remaining_traces:
        traces.pop(key, None)
    if set(traces) != remaining_traces:
        raise ValueError("Unbound or missing camera trace")
    return {**metadata, "models":models, "traces":traces}


def encoded(catalog):
    return (json.dumps(catalog,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Write a fresh candidate file under dist instead of checking the catalog')
    args = parser.parse_args(argv)
    catalog = rebuild(ROOT)
    data = encoded(catalog)
    if args.output:
        target = (ROOT / args.output).resolve()
        if not target.is_relative_to(ROOT / 'dist'):
            parser.error('--output must be a fresh file under dist')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    elif (ROOT / CATALOG).read_bytes() != data:
        raise ValueError('Maintained chart catalog differs from frozen research: '+str(CATALOG))
    print(f"{len(catalog['models'])} models, {len(catalog['traces'])} traces, SHA-256 {hashlib.sha256(data).hexdigest()}")


if __name__ == '__main__':
    main()
