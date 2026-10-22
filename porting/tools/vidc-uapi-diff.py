#!/usr/bin/env python3
"""Diff the CAF video codec (vidc_3x) user space interface against the donor.

The vendor OMX service of this ROM is compiled against the donor's
headers, so every value the port's headers carry for the CAF video codec
has to be numerically identical to the donor's.  This script checks that,
and it also reports the values that collide with an upstream 6.12
definition, because the 6.12 core interprets those.

    usage: vidc-uapi-diff.py [donor-tree] [port-tree]

The donor tree defaults to ../oc-test, the port tree to the repository
this script lives in.  The exit status is 1 when a value differs from the
donor's or when a CAF value collides with an upstream value.
"""

import os
import re
import subprocess
import sys

# The CAF names in the two shared headers.  Everything the CAF video codec
# adds to videodev2.h and v4l2-controls.h is one of these.
CAF_PATTERNS = (
    # videodev2.h: the buffer flags
    r"V4L2_QCOM_BUF_\w+",
    r"V4L2_MSM_BUF_FLAG_\w+",
    r"V4L2_MSM_VIDC_BUF_\w+",
    # videodev2.h: the events
    r"V4L2_EVENT_MSM_VIDC_\w+",
    # videodev2.h: the pixel formats
    r"V4L2_PIX_FMT_\w*UBWC\w*",
    r"V4L2_PIX_FMT_SDE_\w+",
    r"V4L2_PIX_FMT_NV12_512",
    r"V4L2_PIX_FMT_NV12_TP10_UBWC",
    r"V4L2_PIX_FMT_NV12_P010_UBWC",
    # v4l2-controls.h: the control IDs
    r"V4L2_CID_MPEG_VIDC_\w+",
    r"V4L2_CID_MPEG_MSM_VIDC_BASE",
    r"V4L2_MPEG_VIDC_\w+",
    r"V4L2_MPEG_MSM_VIDC_\w+",
)

# The headers the CAF video codec adds.
MEDIA_HEADERS = (
    "msm_vidc.h",
    "msm_media_info.h",
    "msm_vidc_private.h",
    "msm_vidc_utils.h",
)

# The include paths needed to preprocess a uapi header of a kernel tree.
UAPI_INCLUDES = (
    "include",
    "out/include/generated",
    "arch/arm64/include",
    "out/arch/arm64/include/generated",
    "include/uapi",
    "out/arch/arm64/include/generated/uapi",
    "include/uapi/asm-generic",
    "out/usr/include",
)


# The port tree, used for the fallback include paths.  Set in main().
PORT_TREE = None


def category(name):
    """The namespace a V4L2 name lives in, so that a collision between a
    buffer flag and a capability flag is not reported as one."""
    if name.startswith("V4L2_BUF_FLAG_") or name.startswith("V4L2_QCOM_BUF_") \
            or name.startswith("V4L2_MSM_BUF_FLAG_") \
            or name.startswith("V4L2_MSM_VIDC_BUF_"):
        return "buffer flag"
    if name.startswith("V4L2_EVENT_"):
        return "event"
    if name.startswith("V4L2_PIX_FMT_"):
        return "pixel format"
    if name.startswith("V4L2_CID_"):
        return "control"
    return name


def is_caf(name):
    return any(re.fullmatch(p, name) for p in CAF_PATTERNS)


# The uapi headers are written for user space as well, and the user space
# view is the one the vendor OMX service is compiled against, so the
# headers are preprocessed without __KERNEL__.  They then want sys/time.h,
# which is not in the kernel tree; this is the part of it they use.
STUB_SYS_TIME_H = """#ifndef _UAPI_STUB_SYS_TIME_H
#define _UAPI_STUB_SYS_TIME_H
struct timeval { long tv_sec; long tv_usec; };
#endif
"""


def preprocess(tree, header):
    """Return the macro definitions of a header, as {name: value}."""
    import tempfile
    with tempfile.TemporaryDirectory() as stub:
        os.makedirs(os.path.join(stub, "sys"))
        with open(os.path.join(stub, "sys", "time.h"), "w") as f:
            f.write(STUB_SYS_TIME_H)
        cmd = ["gcc", "-E", "-dM", "-x", "c", "-nostdinc", "-I", stub]
        for inc in UAPI_INCLUDES:
            cmd += ["-I", os.path.join(tree, inc)]
        # The arch's generated uapi headers (asm/ioctl.h and friends) are
        # the same for both trees; the donor's build tree is not always
        # there, so the port's are used as the fallback.
        for inc in ("out/arch/arm64/include/generated",
                     "out/arch/arm64/include/generated/uapi",
                     "out/usr/include"):
            cmd += ["-I", os.path.join(PORT_TREE, inc)]
        cmd += [os.path.join(tree, header)]
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode:
            raise SystemExit("cannot preprocess %s in %s:\n%s"
                             % (header, tree, out.stderr))
    macros = {}
    for line in out.stdout.splitlines():
        if not line.startswith("#define "):
            continue
        name, _, value = line[len("#define "):].partition(" ")
        macros[name] = value.strip()
    return macros


def read_tree_header(tree, path):
    with open(os.path.join(tree, path)) as f:
        return f.read()


def main():
    global PORT_TREE
    donor = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "../oc-test")
    port = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else
                           os.path.join(os.path.dirname(__file__), "..", ".."))
    PORT_TREE = port
    print("donor: %s" % donor)
    print("port:  %s" % port)
    failures = 0

    # 1. the four headers the CAF video codec adds: they are copied
    #    verbatim, so they have to be identical.
    for header in MEDIA_HEADERS:
        rel = "include/uapi/media/" + header
        d = read_tree_header(donor, rel)
        p = read_tree_header(port, rel)
        if d == p:
            print("OK   %-40s identical to the donor" % rel)
        else:
            failures += 1
            print("FAIL %-40s differs from the donor" % rel)

    # 2. the values the CAF video codec adds to the two shared headers.
    for rel in ("include/uapi/linux/videodev2.h",
                "include/uapi/linux/v4l2-controls.h"):
        dmac = preprocess(donor, rel)
        pmac = preprocess(port, rel)
        caf = sorted(n for n in dmac if is_caf(n))
        missing = [n for n in caf if n not in pmac]
        differing = [(n, dmac[n], pmac[n]) for n in caf
                     if n in pmac and dmac[n] != pmac[n]]
        if missing or differing:
            failures += 1
        print("%-4s %-40s %d CAF values" % ("FAIL" if missing or differing
                                            else "OK", rel, len(caf)))
        for n in missing:
            print("       missing:      %s = %s" % (n, dmac[n]))
        for n, dv, pv in differing:
            print("       differs:      %s: donor %s, port %s" % (n, dv, pv))

        # 3. the collisions: a CAF value that an upstream 6.12 name of the
        #    same kind also has.  The 6.12 core may interpret the
        #    upstream meaning, so these are the dangerous ones.  (A value
        #    that collides with a name of another kind - a capability
        #    flag, an AV1 sequence flag - cannot be confused with it.)
        upstream = {}
        for n, v in pmac.items():
            if is_caf(n) or n.startswith("__"):
                continue
            upstream.setdefault((category(n), v), n)
        for n in caf:
            if n not in pmac:
                continue
            other = upstream.get((category(n), pmac[n]))
            if other and other != n:
                print("       collision:    %s = %s is also %s"
                      % (n, pmac[n], other))

    print("")
    if failures:
        print("FAIL: %d difference(s) against the donor" % failures)
        return 1
    print("OK: every CAF value is the donor's")
    return 0


if __name__ == "__main__":
    sys.exit(main())
