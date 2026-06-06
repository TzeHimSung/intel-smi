#!/usr/bin/env sh
set -eu

PREFIX="${PREFIX:-/usr/local}"
BINDIR="${BINDIR:-$PREFIX/bin}"
SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

install -d "$BINDIR"
install -m 0755 "$SOURCE_DIR/intel_smi.py" "$BINDIR/intel-smi"
ln -sfn "$BINDIR/intel-smi" "$BINDIR/b50-smi"

echo "Installed:"
echo "  $BINDIR/intel-smi"
echo "  $BINDIR/b50-smi -> $BINDIR/intel-smi"
