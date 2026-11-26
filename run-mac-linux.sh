#!/bin/sh
# Launcher for macOS and Linux.
# Finds Python 3 (or tells you how to install it), then runs bridge_mode.py.
# Usage:  sh run-mac-linux.sh [--status | --disable] [other options]

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

python_ok() {
    # True if "$1" exists AND really runs Python 3.6 or newer.
    # (On a fresh Mac, /usr/bin/python3 exists but is only a stub that asks you
    # to install the developer tools, so we actually run it to check.)
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)' >/dev/null 2>&1
}

PYTHON=""
for candidate in python3 python; do
    if python_ok "$candidate"; then
        PYTHON=$candidate
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    echo "  Python 3 is not installed (or is too old). This tool needs Python 3.6 or newer."
    echo ""
    case "$(uname -s 2>/dev/null)" in
        Darwin)
            echo "  How to install it on a Mac (pick ONE):"
            echo ""
            echo "    A) Download the installer from:"
            echo "         https://www.python.org/downloads/macos/"
            echo "       Open the downloaded .pkg file and click through the installer."
            echo ""
            echo "    B) Or type this in Terminal and click 'Install' in the window that pops up:"
            echo "         xcode-select --install"
            ;;
        Linux)
            echo "  How to install it on Linux (type the line for your system in a terminal):"
            echo ""
            echo "    Ubuntu / Debian / Linux Mint / Raspberry Pi OS:"
            echo "         sudo apt update && sudo apt install -y python3"
            echo "    Fedora / RHEL / CentOS:"
            echo "         sudo dnf install -y python3"
            echo "    Arch / Manjaro:"
            echo "         sudo pacman -S python"
            echo "    openSUSE:"
            echo "         sudo zypper install python3"
            echo ""
            echo "    Other systems: https://www.python.org/downloads/source/"
            ;;
        *)
            echo "  Download it from: https://www.python.org/downloads/"
            ;;
    esac
    echo ""
    echo "  When it is installed, close this window, open a new one and run this again."
    echo ""
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/bridge_mode.py" "$@"
