# SCIP → AGE code-graph ingestion — grounding spike

**Date:** 2026-06-02 · **Status:** spike complete, model validated on Go · **Author:** Claude (Opus) + Ian

## Purpose

Before designing the code-graph ingester (SCIP index → Apache AGE property graph), validate the **actual** SCIP data model against ground truth rather than assumptions — the same "prove it before building on it" discipline used for the AGE substrate (BILL-52). This spike ran `scip-go` over a tiny synthetic Go module whose every symbol and relationship is known in advance, then dissected the emitted index.

**Bottom line:** the full code graph (vertices + CONTAINS/DEFINES/CALLS/IMPLEMENTS/REFERENCES) is cleanly reconstructible from a SCIP index. Two non-obvious mechanics — interface-dispatch indirection and `enclosing_range` for caller attribution — are documented below and must be designed for.

---

## 1. Tooling reality (changed since the project's public docs)

The SCIP toolchain **migrated GitHub orgs**: `sourcegraph/*` → **`scip-code/*`** (the `scip-code` org was created 2026-01-09; repos transferred with full history — `gh api repos/sourcegraph/scip-go` now resolves to `scip-code/scip-go`, 2022 creation date and 68★ carried over, dedicated domain `scip-code.org`). This is a legitimate spin-out, **not** a typosquat — confirmed by the fact that Sourcegraph's own checksummed `go.mod` (served by the Go module proxy) declares the module path as `github.com/scip-code/scip-go`.

### Install (validated)

```bash
# Indexer — single 17MB static Go binary, uses go/packages (the real Go typechecker)
go install github.com/scip-code/scip-go/cmd/scip-go@latest      # → ~/go/bin/scip-go  (v0.2.7)
```

### Reading an index — `scip` CLI does NOT `go install`

`go install github.com/scip-code/scip/cmd/scip@latest` **fails**: the `scip` repo's `go.mod` contains `replace` directives, which Go forbids for `go install` of a main package. Two options:

- **(used here, recommended for our Python ingester's equivalent)** read the protobuf directly via the SCIP Go bindings — a ~20-line program (see Appendix A). The bindings (`github.com/scip-code/scip/bindings/go/scip`, v0.8.0) are pulled in transitively by `scip-go`, so they're already cached.
- clone-build the CLI: `git clone https://github.com/scip-code/scip && cd scip && go build ./cmd/scip` (clone-build honors the `replace` directives that block `go install`).

> For the real ingester (Python, in `rag-service/`) we won't use the Go bindings — we'll parse the protobuf via Python. The `scip` CLI's `scip print --json` is the easiest cross-language path; bundle a built `scip` binary, or generate Python protobuf bindings from `scip.proto`.

---

## 2. The synthetic test module

`/tmp/scip-spike/` — two packages, deliberately exercising every edge type:

- `shapes/shape.go`: `Shape` interface (`Area() float64`), `Circle` struct (`R float64`) with method `Area()` that **implicitly** satisfies `Shape` (Go has no `implements` keyword — `scip-go` must infer it).
- `main.go`: `describe(s shapes.Shape)` calls `s.Area()` (interface call); `main()` constructs `Circle`, calls `describe`, calls `fmt.Println` (stdlib call).

This covers: package/type/method/field vertices, cross-package reference, concrete call, interface call, stdlib call, and interface satisfaction at both type and method level.

---

## 3. SCIP data model, as observed

### Index structure

`scip.Index` (protobuf) = `{ metadata, documents[], external_symbols[] }`.
- `metadata`: `tool_info {name:"scip-go", version:"0.2.7"}`, `project_root: file:///tmp/scip-spike`, `text_document_encoding: UTF8`.
- `documents[]`: one per source file — `{ language, relative_path, occurrences[], symbols[] }`.
- `external_symbols[]`: **empty here** — stdlib (`fmt.Println`) was *referenced* but not given a `SymbolInformation` entry (we didn't index `fmt`). Important consequence below.

### 3.1 Symbol monikers — the stable node key

Grammar: `<scheme> <manager> <package> <version> <descriptor>`. Real examples:

```
scip-go gomod scipspike .  scipspike/describe().
scip-go gomod scipspike .  `scipspike/shapes`/Circle#Area().
scip-go gomod scipspike .  `scipspike/shapes`/Shape#
scip-go gomod scipspike .  `scipspike/shapes`/Circle#R.
```

- `version` is `.` for the **indexed module itself** (local); dependencies carry real versions. → normalization note in §5.
- The **descriptor** encodes scope + kind via suffix:

  | Suffix | Meaning | Example |
  |---|---|---|
  | `/` | package / namespace | `` `scipspike/shapes`/`` |
  | `#` | type (struct/interface) | `Circle#`, `Shape#` |
  | `().` | function / concrete method | `describe().`, `Circle#Area().` |
  | `.` | term — field **or** interface method spec | `Circle#R.`, `Shape#Area.` |

  ⚠️ A field ref and an interface-method-spec ref **both** end in `.` — you cannot tell them apart by suffix alone. Use the `kind` field (below).

The full moniker string is **globally unique and stable** → it is the `MERGE` key for idempotent loading into AGE.

### 3.2 `kind` is populated explicitly — **by scip-go only**

Every `SymbolInformation` from `scip-go` carries a `kind`: `Package, Struct, Interface, Method, MethodSpecification, Function, Field, Variable`. (`MethodSpecification` = an interface's method declaration, distinct from a concrete `Method`.)

> ⚠️ **AMENDED in Part 2:** `kind` is **NOT** populated by `scip-typescript@0.4.0` or `scip-python@0.6.6` — both leave it empty. So `kind` is **not** a portable vertex-type signal. The ingester must derive vertex type from the **descriptor suffix** (the SCIP-standard grammar in §3.1), using `kind` only as an enhancement when present (notably to identify Go's `MethodSpecification`, which the suffix alone can't distinguish from a field). See Part 2.

### 3.3 Occurrences

`{ range, symbol, symbol_roles, enclosing_range? }`:
- `range`: `[startLine, startChar, endChar]` (single-line) or `[startLine, startChar, endLine, endChar]`. **The definition range is the *name token only***, not the body.
- `symbol_roles`: bitmask. Observed: **Definition = 1**, **ReadAccess = 8**. (Full set: Import=2, WriteAccess=4, Generated=16, Test=32, ForwardDefinition=64.)
- **`enclosing_range`**: present on **definition** occurrences of functions/methods — the **full body span**. e.g. `describe()` name token `[11,5,13]` but `enclosing_range [11,0,13,1]`. This is the clean basis for caller attribution (§4.3).

### 3.4 Relationships — interface satisfaction

`SymbolInformation.relationships[]` with booleans `is_implementation / is_reference / is_type_definition / is_definition`. `scip-go` emits `is_implementation` at **both** levels:

```
Circle#         -[is_implementation]-> Shape#          (struct implements interface)
Circle#Area().  -[is_implementation]-> Shape#Area.     (method implements method spec)
```

Go's implicit interface satisfaction is captured precisely — no source annotation needed.

---

## 4. Mapping to the AGE graph

### 4.1 Vertices (label ← `kind`)

| SCIP `kind` | AGE label | Key |
|---|---|---|
| Package | `Package` | moniker |
| Struct, Interface | `Type` (prop `kind`) | moniker |
| Function, Method | `Function` (prop `method=bool`) | moniker |
| MethodSpecification | `Function` (prop `interface_method=true`) | moniker |
| Field | `Field` | moniker |
| Variable / `local N` | **skip** (function-scoped, not globally addressable) | — |

Each vertex also stores: `file_path`, `range` (name token, for the "clickable" jump), `enclosing_range` (for functions). `File` vertices come from `documents[].relative_path`.

### 4.2 Structural edges

- **CONTAINS**: from descriptor nesting — `Package` → `Type` → `Method`/`Field`. (Parse the descriptor, or use the document + scope.) Also `File` —CONTAINS→ the symbols it defines (definition occurrences).
- **DEFINES**: `File` → symbol, from definition occurrences (`role & 1`).
- **REFERENCES**: symbol → symbol, from read occurrences (`role & 8`) — the general "X is used at this location" edge.

### 4.3 CALLS — the one real algorithm (validated)

For each **reference** occurrence whose symbol is callable, find the **definition** whose `enclosing_range` contains the reference position → that definition is the caller.

- "callable" = `kind ∈ {Function, Method, MethodSpecification}`, **or** (kind unknown, e.g. stdlib) descriptor ends in `().`.
- `enclosing_range` makes this exact — **no body-span approximation needed**.

Validated output on the synthetic module:

```
describe()  ──CALLS──▶  Shape#Area.   (MethodSpecification — interface call)
main()      ──CALLS──▶  Println().    (EXTERNAL/stdlib — kind unknown, suffix fallback)
main()      ──CALLS──▶  describe().   (Function)
```

### 4.4 IMPLEMENTS + interface dispatch

From `is_implementation` relationships → `Type -[IMPLEMENTS]-> Type` and `Function -[IMPLEMENTS]-> Function(interface_method)`.

**Key interaction:** an interface call lands on the method *spec*, not the concrete method. The concrete target is reached by traversing IMPLEMENTS **in reverse**:

```
describe ──CALLS──▶ Shape#Area.  ◀──IMPLEMENTS── Circle#Area().
```

→ "what concrete code can run when `describe` calls `Area()`?" = `MATCH (caller)-[:CALLS]->(spec)<-[:IMPLEMENTS]-(concrete)`. Store both edges; let Cypher resolve dispatch at query time.

---

## 5. Gotchas & design decisions

1. **Interface dispatch indirection** (§4.4) — CALLS to an interface never points at concrete code directly. The graph must carry IMPLEMENTS to resolve it. Don't try to "flatten" dispatch at ingest; keep it a traversal.
2. **`enclosing_range` is the caller-attribution mechanism** — use it, do not approximate caller bodies from name-token ranges.
3. **External / cross-package callees have no `SymbolInformation` unless those packages are indexed.** `fmt.Println` appeared only as an occurrence symbol (no `kind`, no relationships). Decision needed: (a) create lightweight stub `External` vertices keyed by moniker so CALLS edges have a target, vs (b) only edge to indexed symbols and drop external calls. Recommend (a) — stubs preserve "calls into stdlib/deps" signal cheaply.
4. **Field vs interface-method-spec ambiguity** — both end in `.`; disambiguate via `kind`, never the suffix.
5. **`version` is `.` for the indexed module, real for deps** — when MERGE-keying on the moniker, the local module's `.` is stable per-index but two repos that both index a shared dep will produce the dep's symbols with matching versioned monikers (good — they dedupe). Worth a normalization pass if we ever rewrite the local `.` to a repo identifier.
6. **`local N` symbols** (function-scoped locals) are not globally addressable — skip as vertices.
7. **Idempotent load**: `MERGE` on the full moniker string. Re-indexing a repo updates in place. (Pairs with the AGE `code_graph` bootstrap already in `schema/004_age.sql`.)

---

## 6. Language-neutrality & next steps

The moniker grammar, occurrence/role model, `enclosing_range`, and `relationships` are **SCIP-standard, not Go-specific** — so `scip-python` and `scip-typescript` emit the same shape, and **one ingester consumes all three**. What varies per indexer and must be re-validated:

- **`scheme`** differs (`scip-python`, `scip-typescript`) — fine, it's part of the key.
- **`kind` completeness** and **relationship support** may differ — e.g. Python's structural/duck typing means interface-style `is_implementation` will be sparser than Go's; TS has its own `implements`/`extends`.
- **`enclosing_range` emission** must be confirmed per indexer (Go has it; verify for the others before relying on it for CALLS).

**Validation spikes:**
1. ✅ `scip-python@0.6.6` — validated on a synthetic module (**Part 2**).
2. ✅ `scip-typescript@0.4.0` — validated on a synthetic module (**Part 2**).
3. ⏳ Real-repo scale, still pending: `scip-go` on `~/louis14` (clean Go) and `~/mazzy` (mixed Go+Python → two indexers, two language-islands; cross-language calls are invisible to SCIP); `scip-python` on `rag-service/`; `scip-typescript` on `~/lyos/mobile-v2`.

Then: draft the concrete AGE schema migration + the Python ingester (`scip print --json` → batched Cypher `MERGE`), and wire it next to the existing pgvector ingestion in `rag-service/`.

---

# Part 2 — Cross-indexer validation (scip-python, scip-typescript)

**Date:** 2026-06-02 · Same synthetic module shape (`Shape` interface/ABC + `Circle` impl + `describe` caller) re-authored in Python and TypeScript, indexed and read with the **same** Go reader (Appendix A) — proving the reader and the planned ingester are genuinely language-neutral at the protobuf layer.

- `scip-typescript@0.4.0` — npm `@sourcegraph/scip-typescript`. Run: `scip-typescript index` (reads `tsconfig.json`).
- `scip-python@0.6.6` — npm `@sourcegraph/scip-python`. Run: `scip-python index . --project-name N --project-version V --output index.scip`.

> Note: the **npm packages did NOT migrate** to `scip-code` — they're still `@sourcegraph/*`. Only the Go repos (`scip-go`, `scip`) moved orgs.

## What's identical across all three (the portable core)

| Capability | scip-go | scip-typescript | scip-python |
|---|---|---|---|
| Moniker grammar `<scheme> <mgr> <pkg> <ver> <descriptor>` | ✅ | ✅ | ✅ |
| `enclosing_range` on definitions (→ CALLS works) | ✅ | ✅ | ✅ |
| `symbol_roles` (Definition=1, Read=8) | ✅ | ✅ | ✅ |
| `is_implementation` relationships | ✅ implicit-iface | ✅ explicit `implements` | ✅ inheritance (incl. stdlib `abc.ABC`) |
| CALLS via enclosing-range enclosure | ✅ | ✅ | ✅ |

So **one ingester consumes all three.** CALLS, IMPLEMENTS, and the stable-moniker key all transfer.

## Where they diverge (and what the ingester must do)

1. **`kind` is scip-go-only.** TS and Python emit **no `kind`** → vertex type **must** come from the descriptor suffix (`/`=pkg/module, `#`=type, `().`=callable, `.`=term, `().(x)`=parameter, `:`=Python module). `kind` is a Go-only bonus.

2. **Interface/abstract-method descriptor suffix differs:**
   - Go: `Shape#Area.` (suffix `.`, `kind=MethodSpecification`) — a *bare* `().`-suffix callee filter **misses** Go interface calls.
   - TS/Python: `Shape#area().` (suffix `().`, same as concrete).
   - **Portable callable rule:** `descriptor.endswith('().')  OR  kind ∈ {Function, Method, MethodSpecification, Constructor}`.

3. **Moniker grammar specifics** (all parse the same way, but the pieces differ):
   - Go: `scip-go gomod scipspike . ` + `` `scipspike/shapes`/Circle#Area(). ``
   - TS: `scip-typescript npm scip-ts-spike 1.0.0 ` + `` `shapes.ts`/Circle#area(). `` (the **file** is the namespace; constructor = `` Circle#`<constructor>`(). ``)
   - Python: `scip-python python scippyspike 0.0.1 ` + `shapes/Circle#area().` (the **module** is the namespace; module symbol = `shapes/__init__:`; constructor = `Circle#__init__().`)

4. **`external_symbols` population is inconsistent.** scip-python emits them (stdlib refs get real versioned monikers, e.g. `scip-python python python-stdlib 3.11 abc/ABC#`); scip-go and scip-typescript emitted **0** for these tiny projects. → The "stub `External` vertex keyed by moniker" decision (Part 1 §5.3) is **required**, not optional, for consistent cross-package CALLS targets.

5. **Python decorators surface as CALLS.** `Shape#area().` → `abstractmethod().` appeared because `@abstractmethod` sits inside the method's `enclosing_range`. Decide whether to keep (captures decoration) or filter (a decorator isn't a runtime call). Likely: tag these edges (`via_decorator=true`) rather than drop.

6. **Module-/top-level calls have no function caller.** TS `console.log(describe(new Circle(2)))` at file scope produced no CALLS edge (nothing encloses it as a *function*). To capture "package-level" calls, attribute them to the `File`/`Module` vertex instead of dropping.

7. **`document.language` is set by scip-go but left empty by TS/Python** — don't rely on it; `metadata.tool_info.name` is the reliable language signal.

## Amendments to Part 1

- §3.2 "kind is authoritative" → **kind is scip-go-only**; derive type from the descriptor suffix (done inline above).
- §4.3 callable filter → must be `().`-suffix **OR** `kind`-based (Go method specs); see divergence #2.
- §5.3 external stub vertices → upgraded from "recommended" to **required** (divergence #4).
- New gotcha: decorators-as-CALLS (#5); module-level calls (#6).

## Net conclusion

The SCIP model is portable enough that **a single descriptor-suffix-driven ingester handles Go, Python, and TypeScript**, deriving vertices from suffixes, CALLS from `enclosing_range`, and IMPLEMENTS from `is_implementation`. The per-indexer quirks (no `kind`, Go's `.`-suffix method specs, decorator calls, external-symbol variance) are all handled by the rules above — none require per-language ingester branches beyond the callable-detection rule. Real-repo scale validation (large indexes, `.tsx`, mixed-language `~/mazzy`) is the remaining unknown before building the ingester.

---

# Part 3 — Real-repo scale validation (Go: `~/louis14`, 343 files)

**Date:** 2026-06-02 · Indexed `louis14` (module `louis14`, go 1.26.2, 343 tracked `.go` / 26 source packages) via a **sibling git worktree in `~`** (`~/louis14-scip-wt`) so the cross-module `replace mazarin/textshape => ../mazzy/...` still resolved (a `/tmp` clone would have broken it). scip-go v0.2.7.

## Metrics

| Metric | Value | Implication |
|---|---|---|
| scip-go runtime | **3.0s wall** (17s CPU, parallel) | performance is a non-issue |
| `index.scip` | **15 MB** (~44 KB/file) | → 58 MB JSON; converts in 0.4s, analyzes in 0.8s |
| documents | 318 (incl. **105 `_test.go`**) | deps are NOT emitted as docs; tests ARE |
| symbols | 39,654 — but **32,501 locals (82%)** | filter locals → ~7.1K real vertices |
| occurrences | 234,646 | the edge-source data |
| `external_symbols[]` | **0** | scip-go emits none, even at scale |
| `is_implementation` | 259 | IMPLEMENTS edges |
| CALLS (reconstructed) | **24,424** | real call graph |
| — closure-nested call sites | **0** | enclosure is unambiguous — no innermost-match needed |
| — calls to external/undefined | **8,035 (33%)** | external stubs required |
| `kind` populated | 39,651 / 39,654 | reliable for Go (still Go-only) |
| generics (`[...]` monikers) | 0 | not exercised by this repo — still open |

## Confirmed design decisions

1. **External stub vertices are REQUIRED (Go).** `external_symbols[]` is empty, yet **33% of calls target external code**, visible only as occurrence monikers — which are clean and versioned, so stubbing is mechanical:
   - stdlib → `scip-go gomod github.com/golang/go/src go1.26.2 flag/Int().` (6,909 calls)
   - third-party → `… github.com/dop251/goja …` (370), `github.com/fogleman/gg` (254), `golang.org/x/text` (39)
   - cross-module → `mazarin/textshape …` (468) — the `~/mazzy` dep, captured only because the sibling worktree preserved `../mazzy`
   - **Ingester:** `MERGE (:Symbol {external:true})` per unique external moniker; parse package+version from the moniker.

2. **The enclosure CALLS algorithm needs no innermost-match (for Go).** 0 of 24,424 call sites had >1 enclosing caller — scip-go emits no `enclosing_range` for anonymous closures, so closure-body calls attribute to the enclosing **named** function. Plain containment is correct.

3. **Locals are 82% of symbols — filter them** (`local N`, kind `Variable`). Real graph for louis14 ≈ 7.1K vertices + ~24K CALLS + 259 IMPLEMENTS + references. Small enough that AGE batching is a convenience, not a necessity, at single-repo scale.

4. **Dependencies have no internal structure** — `third_party/gg`, `mazzy/textshape` are referenced by moniker but not emitted as `documents`. The graph has full detail only for *project* code; deps/stdlib are stub-only unless separately indexed. This is the graph's natural, bounded edge.

5. **Test code is in the index** (105 `_test.go` docs). Tag `test:true` on test-origin vertices/edges so queries can include or exclude (recommend include + tag).

## Still open after this pass

- **Generics** — louis14 has none; need a generics-heavy repo to see how type parameters encode in monikers (does `[T]` threaten the MERGE key?).
- **`.tsx` / large TS** — `~/lyos/mobile-v2`.
- **Mixed-language `~/mazzy`** (Go+Python) — two indexers → two disconnected sub-graphs; cross-language calls (Go→Python) are invisible to SCIP.

**Net:** at real single-repo scale the model and reconstruction hold, performance is trivial, and the one hard requirement is **external stub vertices**. Ready to design the AGE schema + Python ingester.

---

## Appendix A — minimal SCIP reader (Go)

```go
package main

import (
	"fmt"; "os"
	"github.com/scip-code/scip/bindings/go/scip"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

func main() {
	data, _ := os.ReadFile(os.Args[1])
	var idx scip.Index
	proto.Unmarshal(data, &idx)
	out, _ := protojson.MarshalOptions{Indent: "  ", UseProtoNames: true}.Marshal(&idx)
	fmt.Println(string(out))
}
```

## Appendix B — reproduce

```bash
go install github.com/scip-code/scip-go/cmd/scip-go@latest
cd <go-module-root> && ~/go/bin/scip-go index      # → index.scip (protobuf)
# read it:
cd /tmp/scip-reader && go mod tidy && go run . <path>/index.scip > index.json
```

Versions at spike time: `scip-go` v0.2.7, `scip` bindings v0.8.0, Go 1.26.2, darwin/arm64.
