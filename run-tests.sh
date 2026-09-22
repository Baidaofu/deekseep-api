#!/usr/bin/env bash
# Compile and run the Local API gateway test suite on a desktop JVM.
#
# The gateway only needs org.json plus two tiny Android stubs (Context and
# SharedPreferences), so it can be exercised without an emulator or a device.
set -e
cd "$(dirname "$0")"

JSON_JAR="${JSON_JAR:-}"
if [ -z "$JSON_JAR" ]; then
  for candidate in \
    "$HOME/.gradle/caches/modules-2/files-2.1/org.json/json/20180813"/*/json-20180813.jar \
    /usr/share/java/json.jar ; do
    if [ -f "$candidate" ]; then JSON_JAR="$candidate"; break; fi
  done
fi
if [ -z "$JSON_JAR" ] || [ ! -f "$JSON_JAR" ]; then
  echo "org.json jar not found. Set JSON_JAR=/path/to/json.jar" >&2
  exit 1
fi
# Java is a native Windows binary under Git Bash; hand it a Windows path.
if command -v cygpath >/dev/null 2>&1; then
  JSON_JAR="$(cygpath -w "$JSON_JAR")"
fi

OUT="build/test-classes"
rm -rf "$OUT"
mkdir -p "$OUT"

find src tests -name '*.java' > build/sources.txt
javac -encoding UTF-8 -nowarn -cp "$JSON_JAR" -d "$OUT" @build/sources.txt

# MSYS/Cygwin rewrite "C:/..." inside the classpath, so disable path conversion
# for the java invocation when running under Git Bash.
MSYS2_ARG_CONV_EXCL='*' java -cp "$OUT;$JSON_JAR" com.dsmod.probe.LocalApiTest