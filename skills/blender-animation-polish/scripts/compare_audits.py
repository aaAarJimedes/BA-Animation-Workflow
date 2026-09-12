"""Compare two Blender snapshots. Exit 1 means protected state changed or resources are missing."""
import argparse
import json
from pathlib import Path

SCHEMA = "blender-animation-polish/audit-1"


def compare(before, after, mode):
    if before.get("schema") != SCHEMA or after.get("schema") != SCHEMA:
        raise ValueError("Unsupported or mismatched snapshot schema")
    if mode not in {"timing", "animation", "look-only"}:
        raise ValueError("Unknown comparison mode")
    differences = []
    def check(label, a, b):
        if a != b:
            differences.append(label)
    check("scene", before["scene"], after["scene"])
    check("timing", before["timing"], after["timing"])
    check("physics", before["physics"], after["physics"])
    if mode in {"animation", "look-only"}:
        for section in ("actions", "bindings"):
            old, new = before["animation"][section], after["animation"][section]
            for key in sorted(set(old) | set(new)):
                if key not in old and section == "bindings" and mode == "look-only" and key.split(":", 1)[0] in {"Material", "ShaderNodeTree", "World"}:
                    continue
                check("animation." + section + "." + key, old.get(key), new.get(key))
    if mode == "look-only":
        check("inspection_frame (use matching frame/subframe)", before["inspection_frame"], after["inspection_frame"])
        check("active_camera", before["active_camera"], after["active_camera"])
        check("cameras", before["cameras"], after["cameras"])
        check("rigs", before["rigs"], after["rigs"])
        for name, state in before["objects"].items():
            check("objects." + name, state, after["objects"].get(name))
    missing = [row.get("name", "unknown") for group in after["resources"].values() for row in group if row["missing"]]
    if missing:
        differences.append("missing_resources: " + ", ".join(missing))
    manual = [row["name"] for group in after["resources"].values() for row in group if row.get("needs_sequence_check")]
    return {"schema": "blender-animation-polish/comparison-1", "mode": mode, "ok": not differences,
            "differences": differences, "manual_sequence_checks": manual,
            "scope": "Protected recorded fields only; not visual, contact, cache validity or complete dependency validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--mode", choices=("timing", "animation", "look-only"), default="animation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare(json.loads(args.before.read_text(encoding="utf-8-sig")),
                     json.loads(args.after.read_text(encoding="utf-8-sig")), args.mode)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
