#!/bin/bash
set -euo pipefail

exec /usr/bin/unshare --mount --propagation private /bin/bash -c '
  set -euo pipefail
  codex_args=("${@:4}")
  if [[ "$PWD" == "/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent" \
        && "${codex_args[0]:-}" == "exec" ]]; then
    codex_args=(exec --add-dir \
      /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs \
      "${codex_args[@]:1}")
  fi
  /usr/bin/install -d -o wmywb -g wmywb -m 0700 /run/user/1000
  /usr/bin/mount --bind "$1" "$2"
  if [[ -n "${WSL_INTEROP:-}" && -e "$WSL_INTEROP" ]]; then
    /usr/bin/mount --bind /dev/null "$WSL_INTEROP"
  fi
  /usr/bin/umount /proc/sys/fs/binfmt_misc 2>/dev/null || true
  unset WSL_INTEROP WSLENV
  exec /usr/bin/setpriv --reuid=1000 --regid=1000 --clear-groups \
    --no-new-privs --reset-env -- /usr/bin/env \
    XDG_RUNTIME_DIR=/run/user/1000 OTEL_SDK_DISABLED=true \
    "$3" "${codex_args[@]}"
' n19b \
  /usr/local/share/noespire-n19b-empty \
  /mnt/c/Users/wmywb/PycharmProjects/Noespire/.git \
  /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/bin/codex \
  "$@"
