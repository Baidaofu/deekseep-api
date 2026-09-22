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
    """Replace `old` with `new` in `path`, requiring at least one match.

    Idempotent: when `new` is non-empty its presence means the patch is already
    applied.  When `new` is empty (a removal) the absence of `old` means so.
    This matters because insertion anchors such as a method signature stay in
    the file after patching, so testing `old` alone would re-apply the patch.
    """
    text = read(path)
    if new:
        if new in text:
            print("  already patched: %s" % label)
            return
    elif old not in text:
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


def replace_optional(path, old, new, label):
    """Like replace_once but tolerates an already-removed anchor."""
    text = read(path)
    if old not in text:
        print("  already removed: %s" % label)
        return
    write(path, text.replace(old, new, 1))
    print("  removed: %s" % label)


def neutralise_module(upstream, api_root, name):
    """Replace an upstream class with the neutralised version shipped here."""
    target = os.path.join(
        upstream, "module", "src", "com", "dsmod", "probe", name)
    source = os.path.join(api_root, "ci", "neutralized", name)
    if not os.path.isfile(source):
        raise SystemExit("missing neutralised source: %s" % source)
    shutil.copyfile(source, target)
    print("  neutralised: %s" % name)


def _find_matching_brace(text, open_index):
    """Return the index of the '}' matching the '{' at `open_index`.

    Skips string literals, char literals, line comments and block comments so that
    braces inside them cannot unbalance the scan.
    """
    depth = 0
    index = open_index
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
            index += 1
            continue
        if char == "'":
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "'":
                    break
                index += 1
            index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            index += 2
            while index + 1 < length and not (
                    text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise SystemExit("unbalanced braces while stripping a method body")


EMPTY_BODY = "{\n        // Removed in this build.\n    }"


def strip_method_body(path, signature, label):
    """Replace a void method's body with an empty one.

    This removes the method's strings and URLs from the compiled output instead of
    leaving them behind as unreachable code.  Idempotent: re-running replaces the
    already-empty body with itself.  Only valid for void methods.
    """
    text = read(path)
    index = text.find(signature)
    if index < 0:
        raise SystemExit("method not found for %s in %s" % (label, path))
    brace = text.find("{", index + len(signature))
    if brace < 0:
        raise SystemExit("no body found for %s in %s" % (label, path))
    end = _find_matching_brace(text, brace)
    if text[brace:end + 1] == EMPTY_BODY:
        print("  already stripped: %s" % label)
        return
    write(path, text[:brace] + EMPTY_BODY + text[end + 1:])
    print("  stripped: %s" % label)


def _find_statement_end(text, start):
    """Return the index of the ';' ending the statement that begins at `start`.

    Skips string literals, char literals and comments so a ';' inside them does not
    terminate the statement early.
    """
    index = start
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
            index += 1
            continue
        if char == "'":
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "'":
                    break
                index += 1
            index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            index += 2
            while index + 1 < length and not (
                    text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        if char == ";":
            return index
        index += 1
    raise SystemExit("unterminated statement")


def blank_string_constant(path, declaration, label):
    """Replace a String constant's value with an empty literal.

    Used for URL constants whose value spans several concatenated lines.
    Idempotent: the blanked form is detected on a second run.
    """
    text = read(path)
    index = text.find(declaration)
    if index < 0:
        raise SystemExit("constant not found for %s in %s" % (label, path))
    end = _find_statement_end(text, index + len(declaration))
    if text[index:end + 1].strip() == declaration.strip() + ' "";':
        print("  already blanked: %s" % label)
        return
    write(path, text[:index] + declaration + ' "";' + text[end + 1:])
    print("  blanked: %s" % label)


def strip_promotional_content(upstream, api_root):
    """Remove the upstream update check, splash notice, community and sponsor UI.

    The GPL licence dialog and the repository link are deliberately kept: GPL-3.0
    requires the licence notice to be preserved, and attribution is not promotion.
    """
    probe = os.path.join(upstream, "module", "src", "com", "dsmod", "probe")
    main = os.path.join(probe, "Main.java")
    ui = os.path.join(probe, "DeekseepUi.java")
    settings = os.path.join(probe, "SettingsActivity.java")

    # 1. Drop the startup release check entirely (no outbound request, no URL).
    neutralise_module(upstream, api_root, "ModuleUpdateChecker.java")
    replace_once(
        main,
        "            ModuleUpdateChecker.checkOnStartup(act);\n",
        "",
        "Main.java update check",
    )

    # 2. Drop the splash notices: the carrier welcome dialog and the open letter.
    neutralise_module(upstream, api_root, "DeekseepLetter.java")
    for signature, label in (
        ("private void showCarrierWelcomeNoticeIfNeeded(final Activity act)",
         "Main.java carrier welcome notice"),
        ("private void showOpenSourceLetterNoticeIfNeeded(final Activity act)",
         "Main.java open letter notice"),
    ):
        strip_method_body(main, signature, label)

    # 3. Remove the sponsor and community rows from the settings card.
    replace_optional(
        ui,
        "        card.addView(toolActionRow(act, \"ds_project_sponsor\", \"赞助开发者\",\n"
        "                \"\", textColor, subColor,\n"
        "                new View.OnClickListener() {\n"
        "                    @Override public void onClick(View view) { showSponsorDialog(act); }\n"
        "                }));\n"
        "        card.addView(makeDivider(act, divColor));\n"
        "        card.addView(toolActionRow(act, \"ds_project_community\", \"交流群\",\n"
        "                \"\", textColor, subColor,\n"
        "                new View.OnClickListener() {\n"
        "                    @Override public void onClick(View view) { showCommunityChooser(act); }\n"
        "                }));\n"
        "        card.addView(makeDivider(act, divColor));\n",
        "",
        "DeekseepUi.java sponsor + community rows",
    )

    # 4. Remove the "letter to users" row.
    replace_optional(
        ui,
        "        LinearLayout letterRow = new LinearLayout(act);\n"
        "        letterRow.setOrientation(LinearLayout.HORIZONTAL);\n"
        "        letterRow.setGravity(Gravity.CENTER_VERTICAL);\n"
        "        letterRow.setPadding(dp(act, 16), dp(act, 13), dp(act, 16), dp(act, 13));\n"
        "        LinearLayout letterLabels = new LinearLayout(act);\n"
        "        letterLabels.setOrientation(LinearLayout.VERTICAL);\n"
        "        letterLabels.addView(labelText(act, \"留给使用者的信\", 15, text, true));\n"
        "        letterLabels.addView(labelText(act,\n"
        "                \"关于开源、滥用与后续维护的个人说明\",\n"
        "                12, sub, false));\n"
        "        letterRow.addView(letterLabels, new LinearLayout.LayoutParams(\n"
        "                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));\n"
        "        TextView letterChevron = labelText(act, \"›\", 24, sub, false);\n"
        "        letterRow.addView(letterChevron);\n"
        "        letterRow.setClickable(true);\n"
        "        letterRow.setFocusable(true);\n"
        "        letterRow.setBackground(controlBackground(\n"
        "                0x00000000, dark ? 0x24FFFFFF : 0x14000000, 0f));\n"
        "        letterRow.setOnClickListener(new View.OnClickListener() {\n"
        "            @Override public void onClick(View view) {\n"
        "                showLetterToUsersDialog(act, true);\n"
        "            }\n"
        "        });\n"
        "        card.addView(letterRow);\n",
        "",
        "DeekseepUi.java letter row",
    )

    # 5. Empty the three promotional dialogs so their text and URLs are not compiled in.
    for signature, label in (
        ("private static void showSponsorDialog(final Activity act)",
         "DeekseepUi.java showSponsorDialog"),
        ("private static void showCommunityChooser(final Activity act)",
         "DeekseepUi.java showCommunityChooser"),
        ("public static void showLetterToUsersDialog(final Activity act, final boolean force)",
         "DeekseepUi.java showLetterToUsersDialog"),
    ):
        strip_method_body(ui, signature, label)

    # 6. Remove the sponsor entry from the classic settings activity.
    replace_optional(
        settings,
        "        project.addView(actionRow(ModuleGlyphView.SPONSOR,\n"
        "                UiLanguage.text(this, \"赞助开发\", \"Sponsor development\"),\n"
        "                UiLanguage.text(this, \"支持更快地维护和适配\","
        " \"Help speed up maintenance and compatibility work\"),\n"
        "                new View.OnClickListener() { @Override public void onClick(View v)"
        " { showSponsor(); } }));\n"
        "        project.addView(divider());\n",
        "",
        "SettingsActivity.java sponsor row",
    )
    for signature, label in (
        ("private void showSponsor()", "SettingsActivity.java showSponsor"),
        ("private void showWechatSponsorCode()",
         "SettingsActivity.java showWechatSponsorCode"),
    ):
        strip_method_body(settings, signature, label)

    # 7. Blank the group URLs and the user-letter text, and empty the link handlers,
    #    so no invite links or author letter survive in the compiled output.
    blank_string_constant(
        ui, "    private static final String QQ_GROUP_URL =",
        "DeekseepUi.java QQ_GROUP_URL")
    blank_string_constant(
        ui, "    private static final String TELEGRAM_GROUP_URL =",
        "DeekseepUi.java TELEGRAM_GROUP_URL")
    blank_string_constant(
        ui, "    public static final String LETTER_TO_USERS_CONTENT =",
        "DeekseepUi.java LETTER_TO_USERS_CONTENT")
    for signature, label in (
        ("private static void openQqGroup(Activity act)",
         "DeekseepUi.java openQqGroup"),
        ("private static void openTelegramGroup(Activity act)",
         "DeekseepUi.java openTelegramGroup"),
    ):
        strip_method_body(ui, signature, label)

    blank_string_constant(
        ui, "    public static final String LETTER_TO_USERS_TITLE =",
        "DeekseepUi.java LETTER_TO_USERS_TITLE")

    # 8. Drop the closed-edition licence-appeal endpoint (unused in an open build).
    replace_optional(
        ui,
        "                String appealUrl = \"https://license.lllucccian.top"
        "/deepseek/v1/appeal?device=\" + Uri.encode(deviceCode);\n",
        "                String appealUrl = \"\";\n",
        "DeekseepUi.java licence appeal URL",
    )

    # 9. Remove the sponsor/community translation entries.  The GPL licence and
    #    repository strings are kept for attribution.
    catalog = os.path.join(probe, "UiLanguageCatalog.java")
    for entry, label in (
        ('        add("赞助开发", "Sponsor development");\n',
         "catalog sponsor development"),
        ('        add("支持更快地维护和适配", "Help speed up maintenance and compatibility work");\n',
         "catalog sponsor blurb"),
        ('        add("感谢支持持续维护与适配。", "Thank you for supporting ongoing maintenance.");\n',
         "catalog sponsor thanks"),
        ('        add("赞助开发者", "Sponsor the developer");\n',
         "catalog sponsor developer"),
        ('        add("交流群", "Community group");\n', "catalog community group"),
        ('        add("支持持续开发和新版本适配",\n                "Support continued development and new-version compatibility");\n',
         "catalog community blurb"),
        ('        add("感谢支持持续开发与 DeepSeek 版本适配。",\n                "Thank you for supporting continued development and DeepSeek compatibility.");\n',
         "catalog community thanks"),
        ('        add("通过爱发电赞助", "Sponsor via Afdian");\n',
         "catalog sponsor via afdian"),
        ('        add("通过微信赞助", "Sponsor via WeChat");\n',
         "catalog sponsor via wechat"),
    ):
        replace_optional(catalog, entry, "", label)

    # 10. Drop the author name from the generated Magisk CA module metadata.
    cert = os.path.join(probe, "z5.java")
    replace_optional(
        cert,
        '                        + "author=lllucccian\\n"\n',
        '                        + "author=Deekseep\\n"\n',
        "z5.java CA module author (zip)",
    )
    replace_optional(
        cert,
        '                + "version=1.1\\nversionCode=2\\nauthor=lllucccian\\n"\n',
        '                + "version=1.1\\nversionCode=2\\nauthor=Deekseep\\n"\n',
        "z5.java CA module author (system)",
    )


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
    print("stripping promotional content")
    strip_promotional_content(upstream, api_root)
    print("patching build script")
    patch_build_script(upstream)
    print("patching module sources")
    patch_main(upstream)
    patch_ui(upstream)
    print("done")


if __name__ == "__main__":
    main(sys.argv)
