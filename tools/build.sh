#!/bin/zsh
# Build the two macOS helpers analyze-reel needs (Vision OCR and foreground mask).
# Needs Xcode Command Line Tools: xcode-select --install
set -e
cd "${0:A:h}"
swiftc -O src/ocr.swift -o ocr
swiftc -O src/fgmask.swift -o fgmask
echo "Built tools/ocr and tools/fgmask"
