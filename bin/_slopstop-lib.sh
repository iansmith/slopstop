#!/usr/bin/env bash
# _slopstop-lib.sh — Shared helpers sourced by slopstop bin scripts.
# Do not execute directly; source it from the same directory:
#
#   # shellcheck source=_slopstop-lib.sh
#   . "$(dirname "$0")/_slopstop-lib.sh"

# Read a scalar value from a TOML file.
# Usage: toml_get <file> <section> <key>
toml_get() {
    local file="$1" section="$2" key="$3"
    python3 - "$file" "$section" "$key" << 'PYEOF'
import sys, tomllib
_, f, section, key = sys.argv
try:
    with open(f, "rb") as fh:
        cfg = tomllib.load(fh)
    val = cfg.get(section, {}).get(key, "")
    print(val if isinstance(val, str) else "")
except FileNotFoundError:
    pass
PYEOF
}

# Read a top-level (section-less) scalar from a TOML file.
# Usage: toml_get_top <file> <key>
toml_get_top() {
    local file="$1" key="$2"
    python3 - "$file" "$key" << 'PYEOF'
import sys, tomllib
_, f, key = sys.argv
try:
    with open(f, "rb") as fh:
        cfg = tomllib.load(fh)
    val = cfg.get(key, "")
    print(val if isinstance(val, str) else "")
except FileNotFoundError:
    pass
PYEOF
}

# Read a list value from a TOML file (one element per line).
# Usage: toml_get_list <file> <section> <key>
toml_get_list() {
    local file="$1" section="$2" key="$3"
    python3 - "$file" "$section" "$key" << 'PYEOF'
import sys, tomllib
_, f, section, key = sys.argv
try:
    with open(f, "rb") as fh:
        cfg = tomllib.load(fh)
    for v in cfg.get(section, {}).get(key, []):
        print(v)
except FileNotFoundError:
    pass
PYEOF
}

# Map language name → config key in [tools].
# Returns 1 for unrecognised languages.
_tool_key() {
    case "$1" in
        go)                     echo "scip_go" ;;
        python)                 echo "scip_python" ;;
        typescript|javascript)  echo "scip_typescript" ;;
        *) return 1 ;;
    esac
}

# Map language name → one-line install hint.
_tool_install() {
    case "$1" in
        go)         echo "go install github.com/sourcegraph/scip-go/cmd/scip-go@latest" ;;
        python)     echo "npm install -g @sourcegraph/scip-python" ;;
        typescript|javascript) echo "npm install -g @sourcegraph/scip-typescript" ;;
        *)          echo "(see https://scip.dev for indexer install instructions)" ;;
    esac
}
