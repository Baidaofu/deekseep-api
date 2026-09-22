#!/usr/bin/env bash
# Build the Deekseep module with the open Local API enabled.
#
# Usage:
#   ci/build-module.sh [--upstream <dir>] [--out <dir>] [--google-play]
#
# If --upstream is omitted the upstream source is cloned from GitHub at the tag
# named by UPSTREAM_TAG (default v1.7.5).
set -euo pipefail

API_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM_TAG="${UPSTREAM_TAG:-v1.7.5}"
UPSTREAM_REPO="${UPSTREAM_REPO:-https://github.com/lllucccian/Deekseep.git}"
UPSTREAM_DIR=""
OUT_DIR="$API_ROOT/build/artifacts"
GOOGLE_PLAY=false
WORK="$API_ROOT/build/upstream"

while [ $# -gt 0 ]; do
  case "$1" in
    --upstream) UPSTREAM_DIR="$2"; shift 2 ;;
    --out)      OUT_DIR="$2"; shift 2 ;;
    --tag)      UPSTREAM_TAG="$2"; shift 2 ;;
    --google-play) GOOGLE_PLAY=true; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$OUT_DIR"

if [ -n "$UPSTREAM_DIR" ]; then
  UPSTREAM_DIR="$(cd "$UPSTREAM_DIR" && pwd)"
  echo "== using upstream checkout: $UPSTREAM_DIR"
else
  if [ ! -d "$WORK/.git" ]; then
    echo "== cloning $UPSTREAM_REPO @ $UPSTREAM_TAG"
    rm -rf "$WORK"
    git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_REPO" "$WORK"
  else
    echo "== reusing existing checkout: $WORK"
  fi
  UPSTREAM_DIR="$WORK"
fi

echo "== applying Local API patches"
python3 "$API_ROOT/ci/apply-local-api.py" "$UPSTREAM_DIR" "$API_ROOT"

echo "== building module"
if [ "$GOOGLE_PLAY" = true ]; then
  ( cd "$UPSTREAM_DIR/module-universal" && GOOGLE_PLAY_BUILD=true bash build.sh )
  BUILT="$UPSTREAM_DIR/module-universal/ds-probe-universal-google-play.apk"
  NAME="Deekseep-${UPSTREAM_TAG#v}-Open-LocalAPI-google-play.apk"
else
  ( cd "$UPSTREAM_DIR/module-universal" && bash build.sh )
  BUILT="$UPSTREAM_DIR/module-universal/ds-probe-universal.apk"
  NAME="Deekseep-${UPSTREAM_TAG#v}-Open-LocalAPI.apk"
fi

if [ ! -f "$BUILT" ]; then
  echo "build did not produce $BUILT" >&2
  exit 1
fi

cp "$BUILT" "$OUT_DIR/$NAME"
( cd "$OUT_DIR" && sha256sum "$NAME" > "$NAME.sha256" )

echo "== verifying APK contains the gateway"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
if [ -n "$SDK_ROOT" ]; then
  AAPT2="$(find "$SDK_ROOT/build-tools" -mindepth 2 -maxdepth 2 -name aapt2 -type f 2>/dev/null | sort -V | tail -n1)"
  if [ -n "$AAPT2" ]; then
    "$AAPT2" dump badging "$OUT_DIR/$NAME" | head -n 3
  fi
fi

echo
echo "artifact: $OUT_DIR/$NAME"
cat "$OUT_DIR/$NAME.sha256"
