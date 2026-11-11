#!/usr/bin/env bash
# Print OPL in-game udptty broadcasts. The diagnostic OPL build sends each
# IOP tty write to UDP port 18194. The release OPL build sends nothing.
set -euo pipefail
port="${1:-18194}"
echo "listening for UDP ${port} (Ctrl-C to stop)" >&2
exec python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", port))
while True:
    data, _addr = sock.recvfrom(65535)
    sys.stdout.buffer.write(data)
    if not data.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    sys.stdout.flush()
PY
