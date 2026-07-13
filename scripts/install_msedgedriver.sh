#!/usr/bin/env bash
# Download msedgedriver matching the installed Microsoft Edge version (macOS arm64).
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRIVERS_DIR="$ROOT/drivers"
INSTALL_PATH="$DRIVERS_DIR/msedgedriver"

EDGE_APP="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
if [[ ! -x "$EDGE_APP" ]]; then
  echo "Microsoft Edge not found at: $EDGE_APP" >&2
  exit 1
fi

EDGE_VERSION="$("$EDGE_APP" --version | awk '{print $3}')"
MAJOR="${EDGE_VERSION%%.*}"
ARCH="$(uname -m)"
case "$ARCH" in
  arm64) ZIP_NAME="edgedriver_mac64_m1.zip" ;;
  x86_64) ZIP_NAME="edgedriver_mac64.zip" ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

URL="https://msedgedriver.microsoft.com/${EDGE_VERSION}/${ZIP_NAME}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Edge version: $EDGE_VERSION"
echo "Downloading: $URL"
curl -fsSL -o "$TMP_DIR/driver.zip" "$URL"
unzip -q -o "$TMP_DIR/driver.zip" -d "$TMP_DIR"

mkdir -p "$DRIVERS_DIR"
install -m 755 "$TMP_DIR/msedgedriver" "$INSTALL_PATH"
echo "Installed: $INSTALL_PATH"
"$INSTALL_PATH" --version

if [[ -w /usr/local/bin ]]; then
  install -m 755 "$INSTALL_PATH" /usr/local/bin/msedgedriver
  echo "Updated system driver: /usr/local/bin/msedgedriver"
elif command -v sudo >/dev/null 2>&1; then
  echo "Updating /usr/local/bin/msedgedriver (sudo required)..."
  sudo install -m 755 "$INSTALL_PATH" /usr/local/bin/msedgedriver
  echo "Updated system driver: /usr/local/bin/msedgedriver"
else
  echo "Note: could not update /usr/local/bin/msedgedriver; tests use $INSTALL_PATH"
fi
