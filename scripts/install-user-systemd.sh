#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SOURCE="$ROOT_DIR/deploy/systemd"
UNIT_TARGET="$HOME/.config/systemd/user"

mkdir -p "$UNIT_TARGET"
rm -f "$UNIT_TARGET/finance-worker.service"
cp "$UNIT_SOURCE"/finance-*.service "$UNIT_TARGET"/
cp "$UNIT_SOURCE"/finance-app.target "$UNIT_TARGET"/

systemctl --user daemon-reload
systemctl --user enable finance-app.target

echo "Installed user services. Start with:"
echo "  systemctl --user start finance-app.target"
echo "Status:"
echo "  systemctl --user status finance-app.target"
echo "Logs:"
echo "  journalctl --user -u 'finance-*' -f"
