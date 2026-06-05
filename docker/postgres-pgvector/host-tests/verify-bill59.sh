#!/usr/bin/env bash
# verify-bill59.sh — Acceptance tests for BILL-59: slopstop-ingest and
# slopstop-install-hooks.
#
# Tests the two host-side scripts that form the automated re-index layer.
# Most tests are self-contained (no running container needed); the final test
# performs a live ingest against the dev container and verifies the response.
#
# Usage (from repo root):
#   bash docker/postgres-pgvector/host-tests/verify-bill59.sh
#
# The dev container must be running for the live-ingest test.
# SKIP_LIVE=1  — skip the live ingest test.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

assert_repo_root

REPO_ROOT="$(pwd -P)"
BIN_DIR="$REPO_ROOT/bin"
SLOPSTOP_INGEST="$BIN_DIR/slopstop-ingest"
SLOPSTOP_INSTALL_HOOKS="$BIN_DIR/slopstop-install-hooks"

echo "verify-bill59 — slopstop-ingest and slopstop-install-hooks"
echo "---"

# Fail fast if scripts are missing.
for f in "$SLOPSTOP_INGEST" "$SLOPSTOP_INSTALL_HOOKS"; do
    if [ ! -x "$f" ]; then
        printf '  FAIL  %s not executable (run: chmod +x bin/%s)\n' \
            "$(basename "$f")" "$(basename "$f")"
        FAIL=$((FAIL + 1))
    fi
done
[ "$FAIL" -gt 0 ] && { print_summary; exit 1; }

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# Create a minimal fake git repo with a .project-conf.toml.
# Usage: make_test_repo <base-dir> [language]
make_test_repo() {
    local base="$1" lang="${2:-go}"
    local repo="$base/testrepo"
    mkdir -p "$repo/.git/hooks"
    cat > "$repo/.project-conf.toml" << TOML
system = "github"
key    = "test/testrepo"
prefix = "TEST"

[code-graph]
languages    = ["$lang"]
module_root  = "."
TOML
    echo "$repo"
}

# Create an executable fake binary that exits 0.
make_fake_bin() {
    local path="$1"
    mkdir -p "$(dirname "$path")"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$path"
    chmod +x "$path"
}

# Write a ~/.slopstop/config.toml for the given HOME dir.
# Usage: make_slopstop_config <home-dir> <scip_go-path> [scip-cli-path] [rag-url]
make_slopstop_config() {
    local home_dir="$1"
    local scip_go_path="$2"
    local scip_cli_path="${3:-}"
    local rag_url="${4:-http://localhost:1234}"
    local config="$home_dir/.slopstop/config.toml"
    mkdir -p "$home_dir/.slopstop"
    cat > "$config" << TOML
[tools]
scip_go = "$scip_go_path"
scip    = "$scip_cli_path"

[rag]
url = "$rag_url"
TOML
}

# ---------------------------------------------------------------------------
# Temp workspace
# ---------------------------------------------------------------------------

TMPDIR_TEST="$(mktemp -d -t bill59-test-XXXXXX)"
cleanup() { rm -rf "$TMPDIR_TEST"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# slopstop-install-hooks tests
# ---------------------------------------------------------------------------

# T1: creates config template when absent + exits 0
T1_DIR="$TMPDIR_TEST/t1"
mkdir -p "$T1_DIR"
T1_REPO="$(make_test_repo "$T1_DIR")"
T1_CONFIG="$T1_DIR/.slopstop/config.toml"
check "install-hooks: exits 0 creating config template (first run)" \
    env HOME="$T1_DIR" bash "$SLOPSTOP_INSTALL_HOOKS" "$T1_REPO"
check "install-hooks: template written at ~/.slopstop/config.toml" \
    test -f "$T1_CONFIG"
check "install-hooks: template has [tools] section" \
    grep -q '\[tools\]' "$T1_CONFIG"
check "install-hooks: template has [rag] section" \
    grep -q '\[rag\]' "$T1_CONFIG"
# Re-run with empty tool paths must fail
check "install-hooks: exits 1 when tool paths are empty" \
    bash -c "! env HOME='$T1_DIR' bash '$SLOPSTOP_INSTALL_HOOKS' '$T1_REPO'"

# T2: exits 1 when tool binary doesn't exist
T2_DIR="$TMPDIR_TEST/t2"
T2_REPO="$(make_test_repo "$T2_DIR")"
make_slopstop_config "$T2_DIR" "/nonexistent/bin/scip-go"
check "install-hooks: exits 1 when tool binary not found" \
    bash -c "! env HOME='$T2_DIR' bash '$SLOPSTOP_INSTALL_HOOKS' '$T2_REPO'"

# T3: installs symlink when all tools are valid
T3_DIR="$TMPDIR_TEST/t3"
T3_REPO="$(make_test_repo "$T3_DIR")"
T3_FAKE_GO="$T3_DIR/fake-tools/scip-go"
T3_FAKE_INGEST="$T3_DIR/fake-tools/slopstop-ingest"
make_fake_bin "$T3_FAKE_GO"
make_fake_bin "$T3_FAKE_INGEST"
make_slopstop_config "$T3_DIR" "$T3_FAKE_GO"
check "install-hooks: exits 0 when tools are valid" \
    env HOME="$T3_DIR" PATH="$T3_DIR/fake-tools:$PATH" \
    bash "$SLOPSTOP_INSTALL_HOOKS" "$T3_REPO"
check "install-hooks: creates post-merge symlink" \
    test -L "$T3_REPO/.git/hooks/post-merge"
check "install-hooks: symlink points to ~/.slopstop/hooks/post-merge" \
    bash -c "readlink '$T3_REPO/.git/hooks/post-merge' | grep -q '\.slopstop/hooks/post-merge'"

# T4: idempotent — re-running does not change the symlink
check "install-hooks: idempotent (re-run exits 0)" \
    env HOME="$T3_DIR" PATH="$T3_DIR/fake-tools:$PATH" \
    bash "$SLOPSTOP_INSTALL_HOOKS" "$T3_REPO"
check "install-hooks: symlink unchanged after re-run" \
    test -L "$T3_REPO/.git/hooks/post-merge"

# T5: backs up a pre-existing non-slopstop hook
T5_DIR="$TMPDIR_TEST/t5"
T5_REPO="$(make_test_repo "$T5_DIR")"
T5_FAKE_GO="$T5_DIR/fake-tools/scip-go"
T5_FAKE_INGEST="$T5_DIR/fake-tools/slopstop-ingest"
make_fake_bin "$T5_FAKE_GO"
make_fake_bin "$T5_FAKE_INGEST"
make_slopstop_config "$T5_DIR" "$T5_FAKE_GO"
printf '#!/usr/bin/env bash\necho pre-existing\n' > "$T5_REPO/.git/hooks/post-merge"
chmod +x "$T5_REPO/.git/hooks/post-merge"
check "install-hooks: exits 0 with pre-existing hook" \
    env HOME="$T5_DIR" PATH="$T5_DIR/fake-tools:$PATH" \
    bash "$SLOPSTOP_INSTALL_HOOKS" "$T5_REPO"
check "install-hooks: backs up pre-existing hook" \
    test -f "$T5_REPO/.git/hooks/post-merge.slopstop-backup"

# ---------------------------------------------------------------------------
# slopstop-ingest tests
# ---------------------------------------------------------------------------

# T6: exits 1 when .project-conf.toml is missing
T6_DIR="$TMPDIR_TEST/t6"
mkdir -p "$T6_DIR/emptyrepo/.git"
make_slopstop_config "$T6_DIR" "/bin/true"
check "ingest: exits 1 without .project-conf.toml" \
    bash -c "! env HOME='$T6_DIR' bash '$SLOPSTOP_INGEST' '$T6_DIR/emptyrepo'"

# T7: exits 1 when ~/.slopstop/config.toml is missing
T7_DIR="$TMPDIR_TEST/t7"
T7_REPO="$(make_test_repo "$T7_DIR")"
check "ingest: exits 1 without ~/.slopstop/config.toml" \
    bash -c "! env HOME='$T7_DIR' bash '$SLOPSTOP_INGEST' '$T7_REPO'"

# T8: exits 1 when tool path is empty
T8_DIR="$TMPDIR_TEST/t8"
T8_REPO="$(make_test_repo "$T8_DIR")"
make_slopstop_config "$T8_DIR" ""
check "ingest: exits 1 with empty tool path" \
    bash -c "! env HOME='$T8_DIR' bash '$SLOPSTOP_INGEST' '$T8_REPO'"

# T9: exits 0 when RAG is unreachable (never break git hooks)
T9_DIR="$TMPDIR_TEST/t9"
T9_REPO="$(make_test_repo "$T9_DIR")"
T9_FAKE_GO="$T9_DIR/fake-tools/scip-go"
T9_FAKE_SCIP="$T9_DIR/fake-tools/scip"
mkdir -p "$T9_DIR/fake-tools"

# Minimal placeholder .scip file; the fake scip CLI below ignores its input and
# outputs hardcoded JSON, so the binary content does not matter.
T9_FAKE_INDEX="$T9_DIR/fake-index.scip"
printf '\x0a\x00' > "$T9_FAKE_INDEX"

# Fake scip-go: copies the pre-built minimal index to --output <path>.
cat > "$T9_FAKE_GO" << FAKEGOEOF
#!/usr/bin/env bash
out=""
while [ \$# -gt 0 ]; do
    case "\$1" in --output) out="\$2"; shift 2 ;; *) shift ;; esac
done
[ -n "\$out" ] && cp "$T9_FAKE_INDEX" "\$out"
exit 0
FAKEGOEOF
chmod +x "$T9_FAKE_GO"

# Fake scip CLI: outputs minimal SCIP JSON (snake_case, as real scip does).
cat > "$T9_FAKE_SCIP" << 'FAKESCIPEOF'
#!/usr/bin/env bash
# scip print --json <file> → stdout
printf '{"metadata":{"tool_info":{"name":"fake-scip"}},"documents":[]}\n'
exit 0
FAKESCIPEOF
chmod +x "$T9_FAKE_SCIP"

make_slopstop_config "$T9_DIR" "$T9_FAKE_GO" "$T9_FAKE_SCIP" "http://localhost:1234"

check "ingest: exits 0 when RAG unreachable (never break git)" \
    env HOME="$T9_DIR" bash "$SLOPSTOP_INGEST" "$T9_REPO"

# ---------------------------------------------------------------------------
# T10: live ingest against the running dev container
# ---------------------------------------------------------------------------

SKIP_LIVE="${SKIP_LIVE:-0}"
if [ "$SKIP_LIVE" = "1" ]; then
    note "SKIP_LIVE=1 — skipping live ingest test"
elif ! curl -s -o /dev/null -w "%{http_code}" "$RAG_URL/healthz" 2>/dev/null | grep -q "200"; then
    note "dev container not reachable at $RAG_URL — skipping live test (SKIP_LIVE=1 to suppress)"
else
    SCIP_GO_PATH="$(command -v scip-go 2>/dev/null || echo "")"
    SCIP_CLI_PATH="$(command -v scip 2>/dev/null || echo "")"

    if [ -z "$SCIP_GO_PATH" ] || [ -z "$SCIP_CLI_PATH" ]; then
        note "scip-go or scip not on PATH — skipping live test"
        note "  Install: go install github.com/sourcegraph/scip-go/cmd/scip-go@latest"
        note "           go install github.com/sourcegraph/scip/cmd/scip@latest"
    else
        T10_DIR="$TMPDIR_TEST/t10"
        T10_REPO="$T10_DIR/test-go-repo"
        mkdir -p "$T10_REPO"
        # Initialise a real git repo with a fake remote so slopstop-ingest can
        # derive the repo-id as "test/bill59-live-test" instead of the basename.
        git -C "$T10_REPO" init -q
        git -C "$T10_REPO" remote add origin https://github.com/test/bill59-live-test.git
        mkdir -p "$T10_REPO/.git/hooks"
        # Create a minimal self-contained Go module that scip-go can index.
        cat > "$T10_REPO/go.mod" << 'GOMOD'
module example.com/bill59test

go 1.21
GOMOD
        printf 'package main\n\nfunc main() {}\n' > "$T10_REPO/main.go"
        cat > "$T10_REPO/.project-conf.toml" << TOML
system = "github"
key    = "test/bill59-live-test"
prefix = "TEST"

[code-graph]
languages    = ["go"]
module_root  = "."
TOML
        make_slopstop_config "$T10_DIR" "$SCIP_GO_PATH" "$SCIP_CLI_PATH" "$RAG_URL"

        check "ingest: exits 0 on live ingest (go module → dev container)" \
            env HOME="$T10_DIR" bash "$SLOPSTOP_INGEST" "$T10_REPO"

        # The test module has no docstrings, so check AGE vertices instead
        # of ticket_chunks rows — the ingest should create at least a File vertex.
        # Use grep to extract just the numeric count line (skip LOAD/SET messages).
        VERTEX_COUNT="$(docker exec slopstop-rag-dev psql -U postgres -t -c \
            "LOAD 'age'; SET search_path = ag_catalog, public;
             SELECT cnt FROM cypher('code_graph', \$\$
               MATCH (n {repo: 'test/bill59-live-test'}) RETURN count(n) AS cnt
             \$\$) AS (cnt bigint);" \
            2>/dev/null | grep -E '^[[:space:]]*[0-9]+[[:space:]]*$' | tr -d '[:space:]' | head -1)"
        check "ingest: live test created ≥1 AGE vertex for the test module" \
            test "${VERTEX_COUNT:-0}" -ge 1
    fi
fi

# ---------------------------------------------------------------------------

print_summary
