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
except Exception as e:
    print(f"[toml_get] {f}: {e}", file=sys.stderr)
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
except Exception as e:
    print(f"[toml_get_top] {f}: {e}", file=sys.stderr)
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
except Exception as e:
    print(f"[toml_get_list] {f}: {e}", file=sys.stderr)
PYEOF
}

