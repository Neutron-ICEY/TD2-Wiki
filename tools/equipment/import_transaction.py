"""Install a reviewed native import, resuming the same batch after interruption."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


def digest(file):
    if not file.exists():
        return None
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def lock(stream):
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def inside(root, name):
    path = root / name
    if path.resolve() != path or not path.is_relative_to(root) or path == root:
        raise ValueError(f"Invalid import path: {name}")
    return path


def install(root, request):
    state = inside(root, ".cache/equipment-import")
    state.mkdir(parents=True, exist_ok=True)
    marker = state / "pending.json"
    with (state / "writer.lock").open("a+b") as writer:
        lock(writer)  # The OS releases the lock even if the process is killed.
        pending = marker.exists()
        if pending:
            batch = json.loads(marker.read_text("utf8"))
            if batch["identity"] != request["identity"]:
                raise ValueError("Finish pending import first: " + batch["review"])
        elif "entries" in request:
            batch = request
        else:
            return None

        review = inside(root / "dist", batch["review"])
        entries = batch["entries"]
        names = [entry["target"] for entry in entries]
        if (len(set(os.path.normcase(name) for name in names)) != len(names)
                or set(names) != set(request["targets"]) or names[-1] != request["baseline"]):
            raise ValueError("Import target set changed")

        def check(entry):
            target = inside(root, entry["target"])
            current = digest(target)
            if current != entry["before"] and not (pending and current == entry["after"]):
                raise ValueError("Import target changed: " + entry["target"])
            return current == entry["after"]

        def check_data():
            for data in entries[:-1]:
                if digest(inside(root, data["target"])) != data["after"]:
                    raise ValueError("Import target changed: " + data["target"])

        for entry in entries:
            check(entry)
            if entry["after"] != entry["before"]:
                if digest(inside(review, entry["artifact"])) != entry["after"]:
                    raise ValueError("Reviewed payload changed: " + entry["target"])

        staging = state / "install.tmp"
        if not pending:
            with staging.open("w", encoding="utf8") as stream:
                json.dump(batch, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staging, marker)
        for entry in entries:
            is_baseline = entry["target"] == request["baseline"]
            if check(entry):
                if is_baseline:
                    check_data()
                continue
            target = inside(root, entry["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with inside(review, entry["artifact"]).open("rb") as src, staging.open("wb") as out:
                shutil.copyfileobj(src, out)
                out.flush()
                os.fsync(out.fileno())
            if digest(staging) != entry["after"]:
                raise ValueError("Reviewed payload changed: " + entry["target"])
            if target.exists():
                shutil.copymode(target, staging)
            if is_baseline:
                check_data()
            if not check(entry):
                os.replace(staging, target)
        marker.unlink()
        return batch["review"]


if __name__ == "__main__":
    result = install(Path.cwd().resolve(), json.load(sys.stdin))
    print(json.dumps(result))
