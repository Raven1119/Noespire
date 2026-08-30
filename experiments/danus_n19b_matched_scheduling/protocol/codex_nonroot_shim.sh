#!/bin/bash
set -euo pipefail

exec /usr/bin/unshare --mount --propagation private /bin/bash -c '
  set -euo pipefail
  /usr/bin/mount --bind "$1" "$2"
  if [[ -d /run/WSL ]]; then
    /usr/bin/mount --bind "$1" /run/WSL
  fi
  /usr/bin/umount /proc/sys/fs/binfmt_misc 2>/dev/null || true
  unset WSL_INTEROP WSLENV
  exec /usr/sbin/runuser --user noespire_n19b -- "$3" "${@:4}"
' n19b \
  /usr/local/share/noespire-n19b-empty \
  /mnt/c/Users/wmywb/PycharmProjects/Noespire/.git \
  /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/bin/codex \
  "$@"
