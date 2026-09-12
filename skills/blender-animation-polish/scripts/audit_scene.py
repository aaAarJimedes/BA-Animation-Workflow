"""Read-only Blender scene snapshot. Run with Blender --python ... -- --output PATH."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

SCHEMA = "blender-animation-polish/audit-1"


def safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bpy.types.ID):
        return {"type": value.bl_rna.identifier, "name": value.name_full,
                "library": value.library.filepath if value.library else None}
    try:
        return [safe(v) for v in value]
    except TypeError:
        return str(value)


def props(value):
    """Serializable scalar RNA settings plus ID references; not nested collections."""
    result = {}
    for p in value.bl_rna.properties:
        if p.identifier == "rna_type" or p.identifier.startswith("select") or p.identifier in {"show_expanded", "lock"} or p.is_readonly:
            continue
        if p.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
            result[p.identifier] = safe(getattr(value, p.identifier))
        elif p.type == "POINTER":
            v = getattr(value, p.identifier)
            if v is None or isinstance(v, bpy.types.ID):
                result[p.identifier] = safe(v)
    return result


def constraints(owner):
    result = []
    for c in getattr(owner, "constraints", []):
        row = {"type": c.type, "settings": props(c)}
        if hasattr(c, "targets"):
            row["targets"] = [props(t) for t in c.targets]
        result.append(row)
    return result


def curve_record(c):
    result = {"path": c.data_path, "index": c.array_index,
              "settings": props(c), "keys": [], "samples": [], "modifiers": []}
    # Avoid RNA reflection and duplicate coordinate serialization for millions of keys.
    result["keys"] = [
        [list(k.co), list(k.handle_left), list(k.handle_right), k.interpolation,
         k.handle_left_type, k.handle_right_type, k.easing, k.type,
         k.amplitude, k.back, k.period]
        for k in c.keyframe_points
    ]
    result["samples"] = [safe(p.co) for p in c.sampled_points]
    for m in c.modifiers:
        row = {"type": m.type, "settings": props(m)}
        if hasattr(m, "control_points"):
            row["control_points"] = [props(p) for p in m.control_points]
        result["modifiers"].append(row)
    return result


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def action_record(a):
    h = hashlib.sha256()
    count = points = 0
    layout = []
    batches = []
    for li, layer in enumerate(getattr(a, "layers", [])):
        for si, strip in enumerate(layer.strips):
            for bag in getattr(strip, "channelbags", []):
                batches.append(([li, layer.name, si, strip.type, bag.slot_handle], bag.fcurves))
    if not batches and hasattr(a, "fcurves"):
        batches.append((["legacy"], a.fcurves))
    for scope, curves in batches:
        layout.append(scope)
        for c in sorted(curves, key=lambda f: (f.data_path, f.array_index)):
            h.update(json.dumps([scope, curve_record(c)], sort_keys=True, ensure_ascii=False,
                                allow_nan=False, separators=(",", ":")).encode())
            h.update(b"\n")
            count += 1
            points += len(c.keyframe_points) + len(c.sampled_points)
    return {"curves_sha256": h.hexdigest(), "curve_count": count, "point_count": points,
            "layout": layout, "slots": [props(s) for s in getattr(a, "slots", [])],
            "use_frame_range": a.use_frame_range, "frame_range": safe(a.frame_range),
            "frame_start": a.frame_start, "frame_end": a.frame_end,
            "use_cyclic": getattr(a, "use_cyclic", False)}


def driver_record(c):
    row = curve_record(c)
    d = c.driver
    row["driver"] = {"type": d.type, "expression": d.expression, "use_self": d.use_self,
                     "variables": [{"name": v.name, "type": v.type,
                                    "targets": [props(t) for t in v.targets]} for v in d.variables]}
    return row


def strip_record(s):
    row = {"type": s.type, "settings": props(s),
           "fcurves": [curve_record(c) for c in s.fcurves],
           "modifiers": [props(m) for m in s.modifiers]}
    if s.type == "META":
        row["strips"] = [strip_record(c) for c in s.strips]
    return row


def animated_ids():
    seen = set()
    for group in ("objects", "shape_keys", "cameras", "lights", "meshes", "armatures",
                  "curves", "lattices", "materials", "node_groups", "worlds", "scenes",
                  "particles", "grease_pencils"):
        for block in getattr(bpy.data, group, []):
            for item in (block, getattr(block, "node_tree", None)):
                if item is None or item.as_pointer() in seen:
                    continue
                seen.add(item.as_pointer())
                if getattr(item, "animation_data", None):
                    yield item


def binding_record(item):
    ad = item.animation_data
    return {"settings": props(ad),
            "slot": getattr(getattr(ad, "action_slot", None), "identifier", None),
            "drivers": [driver_record(c) for c in ad.drivers],
            "nla": [{"settings": props(t), "strips": [strip_record(s) for s in t.strips]}
                    for t in ad.nla_tracks]}


def cache_record(cache):
    return {k: safe(getattr(cache, k)) for k in
            ("frame_start", "frame_end", "frame_step", "is_baked", "is_outdated",
             "use_disk_cache", "use_external", "filepath", "index", "name") if hasattr(cache, k)}


def packed_resource(block):
    return bool(getattr(block, "packed_file", None) or getattr(block, "packed_files", []))


def resource_snapshot():
    """Actual file references; append provenance is separate and never a dependency."""
    all_ids = [block for prop in bpy.data.bl_rna.properties if prop.type == "COLLECTION"
               for block in getattr(bpy.data, prop.identifier)]
    linked_by_library = {}
    required_libraries = set()
    for block in all_ids:
        lib = getattr(block, "library", None)
        if lib:
            linked_by_library.setdefault(lib.as_pointer(), []).append(block.name_full)
            while lib:
                required_libraries.add(lib.as_pointer())
                lib = lib.parent
    images = []
    for im in bpy.data.images:
        packed = packed_resource(im)
        path = bpy.path.abspath(im.filepath, library=im.library) if im.filepath else ""
        images.append({"name": im.name_full, "source": im.source, "filepath": im.filepath,
                       "resolved": path, "packed": packed, "size": list(im.size),
                       "missing": im.source == "FILE" and not packed and (not path or not Path(path).is_file()),
                       "needs_sequence_check": im.source in {"TILED", "SEQUENCE", "MOVIE"} and not packed})
    libraries = []
    for lib in bpy.data.libraries:
        path = bpy.path.abspath(lib.filepath, library=lib.parent)
        packed = packed_resource(lib)
        dependency = lib.as_pointer() in required_libraries
        libraries.append({"name": lib.name_full, "filepath": lib.filepath, "resolved": path,
                          "packed": packed, "dependency": dependency,
                          "linked_ids": sorted(linked_by_library.get(lib.as_pointer(), [])),
                          "missing": dependency and not packed and not Path(path).is_file()})
    files = []
    for kind in ("sounds", "fonts", "movieclips", "volumes", "cache_files"):
        for block in getattr(bpy.data, kind, []):
            raw = getattr(block, "filepath", "")
            if not raw or raw == "<builtin>":
                continue
            path = bpy.path.abspath(raw, library=block.library)
            packed = packed_resource(block)
            sequence = bool(getattr(block, "is_sequence", False)) or getattr(block, "source", "") == "SEQUENCE"
            files.append({"name": block.name_full, "type": kind, "filepath": raw,
                          "resolved": path, "packed": packed,
                          "missing": not packed and not sequence and not Path(path).is_file(),
                          "needs_sequence_check": sequence and not packed})
    provenance = []
    for block in all_ids:
        weak = getattr(block, "library_weak_reference", None)
        if weak:
            provenance.append({"name": block.name_full, "type": block.bl_rna.identifier,
                               "filepath": weak.filepath, "id_name": weak.id_name,
                               "missing": False, "dependency": False})
    return {"images": images, "libraries": libraries, "files": files, "append_provenance": provenance}


def build_snapshot():
    s = bpy.context.scene
    physical = {"rigid_body": None, "object_caches": {}}
    if s.rigidbody_world:
        w = s.rigidbody_world
        physical["rigid_body"] = {"settings": props(w), "cache": cache_record(w.point_cache)}
    for obj in s.objects:
        for m in obj.modifiers:
            if hasattr(m, "point_cache"):
                physical["object_caches"][obj.name_full + "/" + m.name] = cache_record(m.point_cache)
        for ps in obj.particle_systems:
            physical["object_caches"][obj.name_full + "/particle/" + ps.name] = cache_record(ps.point_cache)
    objects = {}
    rigs = {}
    for obj in s.objects:
        objects[obj.name_full] = {
            "type": obj.type, "parent": safe(obj.parent), "parent_type": obj.parent_type,
            "parent_bone": obj.parent_bone, "parent_inverse": safe(obj.matrix_parent_inverse),
            "matrix_basis": safe(obj.matrix_basis), "matrix_world": safe(obj.matrix_world),
            "constraints": constraints(obj), "rotation_mode": obj.rotation_mode}
        if obj.type == "ARMATURE":
            rigs[obj.name_full] = {
                "bones": {b.name: {"parent": b.parent.name if b.parent else None,
                                    "matrix_local": safe(b.matrix_local), "settings": props(b)}
                          for b in obj.data.bones},
                "pose": {b.name: {"matrix_basis": safe(b.matrix_basis), "constraints": constraints(b),
                                   "settings": props(b)} for b in obj.pose.bones}}
    cameras = {}
    for obj in s.objects:
        if obj.type == "CAMERA":
            cameras[obj.name_full] = {"data": props(obj.data), "dof": props(obj.data.dof),
                                      "stereo": props(obj.data.stereo)}
    animation = {"actions": {a.name_full: action_record(a) for a in bpy.data.actions},
                 "bindings": {item.bl_rna.identifier + ":" + item.name_full: binding_record(item)
                              for item in animated_ids()}}
    return {"schema": SCHEMA, "blender_version": list(bpy.app.version), "source": bpy.data.filepath,
            "inspection_frame": [s.frame_current, s.frame_subframe], "scene": s.name_full,
            "timing": {"fps": s.render.fps, "fps_base": s.render.fps_base,
                       "effective_fps": s.render.fps / s.render.fps_base,
                       "formal_scene_range": [s.frame_start, s.frame_end],
                       "preview_enabled": s.use_preview_range,
                       "preview_range": [s.frame_preview_start, s.frame_preview_end],
                       "markers": [{"name": m.name, "frame": m.frame, "camera": safe(m.camera)}
                                   for m in s.timeline_markers]},
            "physics": physical, "animation": animation, "objects": objects, "rigs": rigs,
            "cameras": cameras, "active_camera": safe(s.camera), "resources": resource_snapshot(),
            "limitations": ["No frame evaluation, render, geometry/contact audit, or cache bake was performed.",
                            "Snapshot is of the active scene; actions/resources include all datablocks.",
                            "Nested RNA collections, custom properties, geometry nodes and all simulation types are not exhaustive.",
                            "Tiled images, sequences and movies need separate frame/tile coverage checks.",
                            "VSE media, external simulation caches and plugin-managed files need separate dependency checks.",
                            "Append provenance records are metadata, not live linked libraries."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    snapshot = build_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
    missing = sum(x["missing"] for group in snapshot["resources"].values() for x in group)
    print(json.dumps({"audit": str(args.output), "actions": len(snapshot["animation"]["actions"]),
                      "missing_resources": missing}, ensure_ascii=False), flush=True)
    if missing:
        raise RuntimeError("Missing external resources; see audit output")


if __name__ == "__main__":
    main()
