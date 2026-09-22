#!/usr/bin/env python3
"""Apply the Local API integration patches to an upstream Deekseep source tree.

Usage:
    apply-local-api.py <upstream-root> <local-api-root>

<upstream-root> is a checkout of https://github.com/lllucccian/Deekseep at the
matching release tag.  <local-api-root> is the root of this repository.

The script is idempotent: running it twice on the same tree is a no-op.
"""

import io
import os
import shutil
import sys


def read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def replace_once(path, old, new, label):
    """Replace `old` with `new` in `path`, requiring at least one match."""
    text = read(path)
    if new in text and old not in text:
        print("  already patched: %s" % label)
        return
    if old not in text:
        raise SystemExit("anchor not found for %s in %s:\n%s" % (label, path, old))
    write(path, text.replace(old, new, 1))
    print("  patched: %s" % label)


def overlay_sources(upstream, api_root):
    """Copy the gateway and payload resolver over the upstream module sources."""
    target_dir = os.path.join(upstream, "module", "src", "com", "dsmod", "probe")
    if not os.path.isdir(target_dir):
        raise SystemExit("upstream module sources not found at %s" % target_dir)
    for name in ("z1.java", "z14.java"):
        source = os.path.join(api_root, "src", "com", "dsmod", "probe", name)
        if not os.path.isfile(source):
            raise SystemExit("missing source: %s" % source)
        shutil.copyfile(source, os.path.join(target_dir, name))
        print("  overlaid: %s" % name)


def patch_build_script(upstream):
    """Make the generated BuildInfo advertise the Local API, and pin UTF-8."""
    build = os.path.join(upstream, "module-universal", "build.sh")
    replace_once(
        build,
        'public static final boolean LOCAL_API_INCLUDED = false;',
        'public static final boolean LOCAL_API_INCLUDED = true;',
        "build.sh LOCAL_API_INCLUDED",
    )
    replace_once(
        build,
        'public static final String BUILD_EDITION = "Open";',
        'public static final String BUILD_EDITION = "Open LocalAPI";',
        "build.sh BUILD_EDITION",
    )
    # Upstream assumes a UTF-8 locale; make that explicit so the build does not
    # depend on the runner's LANG.
    replace_once(
        build,
        "if ! javac -source 8 -target 8 \\",
        "if ! javac -encoding UTF-8 -source 8 -target 8 \\",
        "build.sh javac encoding",
    )


def patch_main(upstream):
    """Skip the Closed-edition license re-enrollment in an open build."""
    main = os.path.join(
        upstream, "module", "src", "com", "dsmod", "probe", "Main.java")
    replace_once(
        main,
        "        if (!CloudPromptClient.hasLocalApiGrant(appContext)) {",
        "        if (BuildInfo.PROTECTED_BUILD"
        " && !CloudPromptClient.hasLocalApiGrant(appContext)) {",
        "Main.java license gate",
    )


def patch_ui(upstream):
    """Un-hide the two Local API settings entries."""
    ui = os.path.join(
        upstream, "module", "src", "com", "dsmod", "probe", "DeekseepUi.java")
    replace_once(
        ui,
        "if (BuildInfo.PROTECTED_BUILD && BuildInfo.LOCAL_API_INCLUDED"
        " && !isClosedV241()) {",
        "if (BuildInfo.LOCAL_API_INCLUDED && !isClosedV241()) {",
        "DeekseepUi.java experimental entry",
    )
    replace_once(
        ui,
        "if (BuildInfo.PROTECTED_BUILD && BuildInfo.LOCAL_API_INCLUDED) {",
        "if (BuildInfo.LOCAL_API_INCLUDED) {",
        "DeekseepUi.java service entry",
    )


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    upstream = os.path.abspath(argv[1])
    api_root = os.path.abspath(argv[2])
    if not os.path.isdir(upstream):
        raise SystemExit("upstream root does not exist: %s" % upstream)

    print("overlaying Local API sources")
    overlay_sources(upstream, api_root)
    print("patching build script")
    patch_build_script(upstream)
    print("patching module sources")
    patch_main(upstream)
    patch_ui(upstream)
    print("done")


if __name__ == "__main__":
    main(sys.argv)
