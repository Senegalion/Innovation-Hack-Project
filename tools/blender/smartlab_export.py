import json
import sys
import urllib.request
import uuid
from pathlib import Path

import bpy

USAGE = """
blender lab.blend --background --python smartlab_export.py -- <out_dir> [--upload <api_url> <lab_id> <user_id>]

Custom properties read from each top-level object (all optional):
  smartlab_id        asset ID (defaults to the object name, e.g. HPLC-04)
  smartlab_name      display name
  smartlab_kind      instrument | bench | hood | freezer | storage
  smartlab_category  category shown on the card
  smartlab_storage   flammables | acids | cold | frozen | general (for cabinets)
  smartlab_skip      1 to treat the object as structure (walls, floor)
"""


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print(USAGE)
        sys.exit(1)
    out_dir = Path(argv[0])
    upload = None
    if "--upload" in argv:
        i = argv.index("--upload")
        upload = argv[i + 1:i + 4]
        if len(upload) != 3:
            print(USAGE)
            sys.exit(1)
    return out_dir, upload


def manifest_entries():
    entries = []
    for obj in bpy.context.scene.objects:
        if obj.parent is not None or obj.type not in {"MESH", "EMPTY"}:
            continue
        entry = {"node": obj.name}
        for key, field in (("smartlab_id", "id"), ("smartlab_name", "name"), ("smartlab_kind", "kind"),
                           ("smartlab_category", "category"), ("smartlab_storage", "storage_class")):
            if key in obj.keys():
                entry[field] = str(obj[key])
        if obj.get("smartlab_skip"):
            entry["skip"] = True
        if len(entry) > 1:
            entries.append(entry)
    return entries


def export(out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(bpy.data.filepath).stem or "lab"
    glb = out_dir / f"{name}.glb"
    manifest = out_dir / f"{name}.smartlab.json"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_yup=True, export_apply=True,
                              export_extras=True, use_selection=False)
    manifest.write_text(json.dumps({"objects": manifest_entries()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return glb, manifest


def upload(api_url: str, lab_id: str, user_id: str, glb: Path, manifest: Path):
    boundary = uuid.uuid4().hex
    body = b""
    for field, path, ctype in (("file", glb, "model/gltf-binary"), ("manifest", manifest, "application/json")):
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{api_url.rstrip('/')}/api/labs/{lab_id}/model", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "X-User-Id": user_id})
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    print(f"Uploaded: {len(result['created'])} created, {len(result['updated'])} updated")


def main():
    out_dir, up = parse_args()
    glb, manifest = export(out_dir)
    print(f"Exported {glb} and {manifest}")
    if up:
        upload(up[0], up[1], up[2], glb, manifest)


main()
