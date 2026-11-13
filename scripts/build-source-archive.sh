#!/bin/sh
# Builds the corresponding-source archive served at /source/archive.
# Run from the repository root. The Dockerfile runs this automatically so a
# deployed instance always offers source matching the code it runs.
set -eu

OUT_DIR="source-archive"
OUT="$OUT_DIR/wingetty-source.tar.gz"
mkdir -p "$OUT_DIR"

VERSION_STAMP="unknown"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    VERSION_STAMP=$(git rev-parse HEAD)
fi
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

for path in app wingetty_import client tests scripts migrations src \
    requirements.txt requirements-dev.txt settings.toml config.py \
    Dockerfile docker-compose.yml tailwind.config.js package.json \
    package-lock.json start.sh README.md LICENSE.md NOTICE.md; do
    [ -e "$path" ] && cp -r "$path" "$STAGE/"
done

find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE" -name '*.pyc' -delete

printf 'source_revision=%s\nbuild_date=%s\n' "$VERSION_STAMP" "$BUILD_DATE" > "$STAGE/SOURCE_VERSION"

tar -czf "$OUT" -C "$STAGE" .
echo "Wrote $OUT (revision $VERSION_STAMP, built $BUILD_DATE)"
