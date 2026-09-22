#!/usr/bin/env bash
# Build the Deekseep module with the reconstructed open Local API enabled.
#
# This is a self-contained build for D:\pi\deekseep that mirrors
# Deekseep/module-universal/build.sh, with three changes:
#   1. -encoding UTF-8, because the upstream script was written for a UTF-8 POSIX
#      locale and Windows javac defaults to GBK.
#   2. The Local API sources from work/api-src/api are overlaid on module/src.
#   3. BuildInfo is generated with LOCAL_API_INCLUDED=true and PROTECTED_BUILD=false,
#      so the Local API UI and gateway are reachable in an open build.
set -e
cd "$(dirname "$0")"

REPO_ROOT="$(cd .. && pwd)"
SRC_REPO="$REPO_ROOT/Deekseep"
OUT="$REPO_ROOT/work/build"
API_SRC="$REPO_ROOT/work/api-src/api"

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/c/Users/Baidaofu/AppData/Local/Android/Sdk}}"
BT="$SDK_ROOT/build-tools/35.0.0"
ANDROID_JAR="$SDK_ROOT/platforms/android-35/android.jar"
AAPT2="$BT/aapt2.exe"
D8="$BT/d8.bat"
ZIPALIGN="$BT/zipalign.exe"
APKSIGNER="$BT/apksigner.bat"

for tool in "$ANDROID_JAR" "$AAPT2" "$D8" "$ZIPALIGN" "$APKSIGNER"; do
  if [ ! -f "$tool" ]; then
    echo "Missing required Android tool: $tool" >&2
    exit 1
  fi
done

RISH_DEX="$SRC_REPO/third_party/shizuku/rish_shizuku.dex"
RISH_SHA256="1953c1fd9708904f8fc1f67774843b4cc3d03e5f2a578ff4d654d0625456bc28"
if [ ! -f "$RISH_DEX" ]; then
  echo "Missing verified Shizuku rish payload: $RISH_DEX" >&2
  exit 1
fi

GOOGLE_PLAY_BUILD="${GOOGLE_PLAY_BUILD:-false}"
if [[ "$GOOGLE_PLAY_BUILD" == "true" ]]; then
  GOOGLE_PLAY_VALUE=true
  APK_NAME="Deekseep-1.7.5-Open-LocalAPI-google-play.apk"
else
  GOOGLE_PLAY_VALUE=false
  APK_NAME="Deekseep-1.7.5-Open-LocalAPI.apk"
fi

rm -rf "$OUT"
mkdir -p "$OUT/classes" "$OUT/dex" "$OUT/generated-src/com/dsmod/probe" "$OUT/src/com/dsmod/probe"

echo "[1/8] overlay Local API sources"
cp "$SRC_REPO"/module/src/com/dsmod/probe/*.java "$OUT/src/com/dsmod/probe/"
cp "$API_SRC"/*.java "$OUT/src/com/dsmod/probe/"

MODULE_VER=$(grep -oE 'android:versionName="[^"]+"' "$SRC_REPO/module-universal/AndroidManifest.xml" \
  | head -n1 | cut -d'"' -f2)

echo "[2/8] generate BuildInfo.java (LOCAL_API_INCLUDED=true)"
cat > "$OUT/generated-src/com/dsmod/probe/BuildInfo.java" <<EOF
package com.dsmod.probe;
public final class BuildInfo {
    public static final String API_VERSION = "universal (Xposed API 82-102 verified)";
    public static final String MODULE_VERSION = "${MODULE_VER:-1.7.5}";
    public static final String BUILD_EDITION = "Open LocalAPI";
    public static final String DISPLAY_VERSION = MODULE_VERSION + " " + BUILD_EDITION;
    public static final String BUILD_DATE = "$(date '+%Y-%m-%d %H:%M')";
    public static final boolean GOOGLE_PLAY = ${GOOGLE_PLAY_VALUE};
    public static final boolean PROTECTED_BUILD = false;
    public static final boolean LOCAL_API_INCLUDED = true;
    public static final String CLOUD_LOCAL_API_PAYLOAD_NAME = "";
    public static final boolean GOOGLE_V241_BASIC = false;
    public static final boolean SHI_V5_V241 = false;
    public static final String SHI_V5_HOST_PACKAGE = "";
    public static final String SHI_V5_HOST_VERSION_NAME = "";
    public static final long SHI_V5_HOST_VERSION_CODE = -1L;
    public static final String SHI_V5_HOST_CERT_SHA256 = "";
    public static final String SHI_V5_HOST_CERT_SHA256_ALT = "";
    public static final String SHI_V5_V236_HOST_VERSION_NAME = "";
    public static final long SHI_V5_V236_HOST_VERSION_CODE = -1L;
    public static final String PROTECTED_PAYLOAD_KEY_A = "";
    public static final String PROTECTED_PAYLOAD_KEY_B = "";
    public static final String PROTECTED_PAYLOAD_IV = "";
    public static final String PROTECTED_PAYLOAD_SHA256 = "";
    public static final String PROTECTED_PAYLOAD_NAME = "";
    public static final String LEGACY_PROTECTED_PAYLOAD_NAME = "";
    public static final String SHI_CORE_SHA256 = "";
    private BuildInfo() {}
}
EOF

echo "[3/8] collect sources"
cp "$SRC_REPO/module/src/com/dsmod/probe/Main.java" \
  "$OUT/generated-src/com/dsmod/probe/Main.java"
# The shipped Closed edition gates the gateway behind a server-side license grant and a
# cloud payload re-enrollment round trip.  In an open build with PROTECTED_BUILD=false
# there is no license server, so make the re-enrollment conditional on PROTECTED_BUILD.
python - "$OUT/generated-src/com/dsmod/probe/Main.java" <<'PY'
import io, sys
path = sys.argv[1]
src = io.open(path, encoding='utf-8').read()
old = """        if (!CloudPromptClient.hasLocalApiGrant(appContext)) {"""
new = """        if (BuildInfo.PROTECTED_BUILD && !CloudPromptClient.hasLocalApiGrant(appContext)) {"""
if old not in src:
    sys.stderr.write('Main.java patch anchor not found\n')
    sys.exit(1)
src = src.replace(old, new, 1)
io.open(path, 'w', encoding='utf-8', newline='').write(src)
print('patched Main.java cloud re-enrollment gate')
PY

# The Local API settings entries are hidden behind PROTECTED_BUILD in the shipped build.
# Reveal them in this open build: LOCAL_API_INCLUDED is already true, so drop the
# PROTECTED_BUILD conjunct from the two menu guards only (not from isClosedV241, which
# selects a version-specific code257 behaviour).
python - "$OUT/src/com/dsmod/probe/DeekseepUi.java" <<'PY'
import io, sys
path = sys.argv[1]
src = io.open(path, encoding='utf-8').read()
replacements = [
    ('if (BuildInfo.PROTECTED_BUILD && BuildInfo.LOCAL_API_INCLUDED && !isClosedV241()) {',
     'if (BuildInfo.LOCAL_API_INCLUDED && !isClosedV241()) {'),
    ('if (BuildInfo.PROTECTED_BUILD && BuildInfo.LOCAL_API_INCLUDED) {',
     'if (BuildInfo.LOCAL_API_INCLUDED) {'),
]
for old, new in replacements:
    if old not in src:
        sys.stderr.write('DeekseepUi.java anchor not found: %s\n' % old)
        sys.exit(1)
    src = src.replace(old, new, 1)
io.open(path, 'w', encoding='utf-8', newline='').write(src)
print('patched DeekseepUi.java Local API menu guards')
PY
# javac @argfile on Windows needs forward slashes without a drive-letter prefix
# when we run from inside the build directory.
(
  cd "$OUT"
  : > sources.txt
  find src/com/dsmod/probe -maxdepth 1 -name '*.java' ! -name Main.java \
    ! -name BuildInfo.java >> sources.txt
  # Upstream sources live outside $OUT; emit them as Windows-style absolute paths
  # (backslashes are fine once the argfile itself uses relative entries).
  find "$SRC_REPO/module/src/com/dsmod/relay" -name '*.java' \
    | while read -r f; do cygpath -w "$f"; done >> sources.txt
  find "$SRC_REPO/module-legacy/compat" -name '*.java' \
    | while read -r f; do cygpath -w "$f"; done >> sources.txt
  find "$SRC_REPO/module-legacy/src/de" -name '*.java' \
    | while read -r f; do cygpath -w "$f"; done >> sources.txt
  find generated-src -name '*.java' >> sources.txt
)

echo "[4/8] javac (androidx PathParser)"
PATH_PARSER_JAR="$OUT/androidx-path-parser.jar"
if [ ! -f "$PATH_PARSER_JAR" ]; then
  AAR="$OUT/core-1.18.0.aar"
  if [ ! -f "$AAR" ]; then
    curl -fsSL --connect-timeout 15 --max-time 180 \
      "https://dl.google.com/dl/android/maven2/androidx/core/core/1.18.0/core-1.18.0.aar" \
      -o "$AAR"
  fi
  unzip -p "$AAR" classes.jar > "$OUT/androidx-core-classes.jar"
  STAGE="$OUT/androidx-path-parser-classes"
  mkdir -p "$STAGE"
  ( cd "$STAGE" && jar xf "$OUT/androidx-core-classes.jar" \
      'androidx/core/graphics/PathParser.class' \
      'androidx/core/graphics/PathParser$ExtractFloatResult.class' \
      'androidx/core/graphics/PathParser$PathDataNode.class' )
  jar cf "$PATH_PARSER_JAR" -C "$STAGE" androidx/core/graphics
fi

JAVAC_ANDROID_JAR="$(cygpath -w "$ANDROID_JAR" 2>/dev/null || echo "$ANDROID_JAR")"
JAVAC_PATH_PARSER="$(cygpath -w "$PATH_PARSER_JAR" 2>/dev/null || echo "$PATH_PARSER_JAR")"
JAVAC_CLASSES="$(cygpath -w "$OUT/classes" 2>/dev/null || echo "$OUT/classes")"
if ! ( cd "$OUT" && javac -encoding UTF-8 -source 8 -target 8 -nowarn \
    -cp "$JAVAC_ANDROID_JAR;$JAVAC_PATH_PARSER" \
    -d "$JAVAC_CLASSES" @sources.txt ) 2> "$OUT/javac.err"; then
  cat "$OUT/javac.err"
  exit 1
fi
grep -v 'warning:' "$OUT/javac.err" || true

echo "[5/8] d8"
MODCLASSES_JAR="$OUT/module-classes.jar"
( cd "$OUT/classes" && jar cf "$MODCLASSES_JAR" com )
"$D8" --min-api 24 --output "$OUT/dex" "$MODCLASSES_JAR" "$PATH_PARSER_JAR" --lib "$ANDROID_JAR"

echo "[6/8] aapt2"
"$AAPT2" compile --dir "$SRC_REPO/module-universal/res" -o "$OUT/res.zip"
"$AAPT2" link -o "$OUT/base.apk" -I "$ANDROID_JAR" \
  --manifest "$SRC_REPO/module-universal/AndroidManifest.xml" \
  -R "$OUT/res.zip" --auto-add-overlay

echo "[7/8] package"
cp "$OUT/base.apk" "$OUT/unsigned.apk"
( cd "$OUT" && jar uf unsigned.apk -C dex classes.dex )
mkdir -p "$OUT/xstage/assets" "$OUT/xstage/META-INF/com.dsmod.probe.agent"
cp "$SRC_REPO/module-universal/assets/xposed_init" "$OUT/xstage/assets/xposed_init"
cp "$RISH_DEX" \
  "$OUT/xstage/META-INF/com.dsmod.probe.agent/.rish_shizuku_runtime_payload.dat"
( cd "$OUT/xstage" && jar uf "$OUT/unsigned.apk" META-INF assets )
"$ZIPALIGN" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

echo "[8/8] sign"
KEYSTORE="$OUT/debug.keystore"
if [ ! -f "$KEYSTORE" ]; then
  keytool -genkeypair -keystore "$KEYSTORE" -storepass android \
    -keypass android -alias androiddebugkey \
    -dname "CN=Deekseep LocalAPI Build,O=Deekseep,C=US" \
    -keyalg RSA -keysize 2048 -validity 10000
fi
"$APKSIGNER" sign --ks "$KEYSTORE" --ks-pass pass:android \
  --key-pass pass:android --out "$APK_NAME" "$OUT/aligned.apk"

echo "DONE -> $(pwd)/$APK_NAME"