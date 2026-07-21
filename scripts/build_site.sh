#!/usr/bin/env bash
# Assemble the MkDocs docs directory (`_web/`) from the book Markdown sources.
# Only Markdown + images are copied; code, PDFs and LaTeX sources are left out
# so the generated site stays small. The original sources are never modified.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/_web"

rm -rf "$DEST"
mkdir -p "$DEST"

# Site homepage (root index.md).
cp "$ROOT/index.md" "$DEST/index.md"

# The language editions, each with its images/ subfolder.
for lang in book book-en book-ta book-vi book-zhtw; do
  mkdir -p "$DEST/$lang"
  cp -R "$ROOT/$lang" "$DEST/"
done

# Copy site-level assets (JS/CSS for the language switcher) that MkDocs
# resolves relative to docs_dir.
cp -R "$ROOT/extras" "$DEST/extras"

# Keep only Markdown and images; drop .tex/.py/.lua/.pdf/.sh etc.
find "$DEST" -type f \
  ! -name '*.md' \
  ! -name '*.svg' \
  ! -name '*.png' \
  ! -name '*.jpg' \
  ! -name '*.jpeg' \
  ! -name '*.js' \
  ! -name '*.css' \
  -delete

echo "Assembled docs into $DEST"
