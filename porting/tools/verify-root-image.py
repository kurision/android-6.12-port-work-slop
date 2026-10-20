#!/usr/bin/env python3
"""Keep run234b's raw kernel/header; accept only the audited Magisk ramdisk delta."""
import gzip
import hashlib
import importlib.util
import json
import lzma
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
spec = importlib.util.spec_from_file_location("packager", REPO / "porting/logging/package-diag-boot.py")
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)


def unpack(data):
    assert data[:8] == b"ANDROID!"
    size, ram_size, page = (struct.unpack_from("<I", data, n)[0] for n in (8, 16, 36))
    assert page == pkg.PAGE
    start = page + pkg.pad(size)
    kernel = data[page:page + size]
    ramdisk = data[start:start + ram_size]
    records, _ = pkg.parse_cpio(gzip.decompress(ramdisk))
    names = [r["name"] for r in records]
    assert len(names) == len(set(names)), "duplicate cpio names"
    return kernel, ramdisk, {r["name"]: r for r in records}


base = (HERE.parent / "boot-run234b.img").read_bytes()
assert pkg.sha256(base) == "dab3ba0c52869f5d4802267a9a17ec037216e86f5512d92209d0fa78429c7bbf"
patched = (HERE / "boot-run234b-magisk30700.img").read_bytes()
kernel, _, old = unpack(base)
new_kernel, ramdisk, new = unpack(patched)

# magiskboot recompresses the kernel; do not ship that incidental change.
old_gz, new_gz = zlib.decompressobj(31), zlib.decompressobj(31)
assert old_gz.decompress(kernel) == new_gz.decompress(new_kernel)
assert old_gz.unused_data == new_gz.unused_data, "appended DTB changed"
assert lzma.decompress(new[".backup/init.xz"]["data"]) == old["init"]["data"]
allowed = {"TRAILER!!!", "init", "overlay.d", "overlay.d/sbin",
           "overlay.d/sbin/magisk.xz", "overlay.d/sbin/stub.xz", "overlay.d/sbin/init-ld.xz"}
changed = []
for name in sorted(old.keys() | new.keys()):
    a, b = old.get(name), new.get(name)
    # magiskboot renumbers cpio inodes. Restore unrelated records exactly.
    if a and b and a["data"] == b["data"] and a["fields"][1:] == b["fields"][1:]:
        new[name] = a
        continue
    if a != b:
        assert name in allowed or name == ".backup" or name.startswith(".backup/"), name
        changed.append(name)

ramdisk = gzip.compress(pkg.build_cpio(list(new.values()), b""), compresslevel=9, mtime=0)

header = bytearray(base[:pkg.PAGE])
struct.pack_into("<I", header, 16, len(ramdisk))
digest = hashlib.sha1(kernel + struct.pack("<I", len(kernel)) + ramdisk +
                      struct.pack("<I", len(ramdisk)) + struct.pack("<I", 0)).digest()
header[pkg.ID_OFF:pkg.ID_OFF + pkg.ID_LEN] = digest.ljust(pkg.ID_LEN, b"\0")
image = bytes(header) + kernel.ljust(pkg.pad(len(kernel)), b"\0") + ramdisk.ljust(pkg.pad(len(ramdisk)), b"\0")
assert len(image) <= pkg.MAX_IMAGE
assert unpack(image)[0] == kernel
assert image[64:576] == base[64:576]
out = HERE / "boot-run234b-root-preserved-kernel.img"
with out.open("xb") as f:
    f.write(image)
report = {"image": str(out), "sha256": pkg.sha256(image), "size": len(image),
          "base_sha256": pkg.sha256(base), "kernel_payload_sha256": pkg.sha256(kernel),
          "ramdisk_sha256": pkg.sha256(ramdisk), "changed_cpio_records": changed,
          "diagnostic_init_backup_matches": True, "cmdline_unchanged": True,
          "magisk_config": new[".backup/.magisk"]["data"].decode()}
with (HERE / "verification.json").open("x") as f:
    json.dump(report, f, indent=2)
    f.write("\n")
print(json.dumps(report, indent=2))
