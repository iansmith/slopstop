#!/usr/bin/env python3
"""Clone detection using ast-grep — no tree-sitter dependency.

Extracts AST blocks via `ast-grep run`, normalizes with stdlib regex,
MD5-hashes the normalized text, and groups by hash. Clone groups with
2+ members are reported.

Dependencies: ast-grep binary on PATH, Python 3.9+ stdlib.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PATTERNS = {
    "python": [
        ("function_definition", "def $FUNC($$$ARGS): $$$BODY"),
        ("if_statement", "if $COND: $$$BODY"),
        ("for_statement", "for $VAR in $ITER: $$$BODY"),
        ("while_statement", "while $COND: $$$BODY"),
        ("with_statement", "with $CTX: $$$BODY"),
        ("try_statement", "try: $$$BODY"),
    ],
    "go": [
        ("function_declaration", "func $FUNC($$$ARGS) $$$RET { $$$BODY }"),
        ("method_declaration", "func ($$$RECV) $FUNC($$$ARGS) $$$RET { $$$BODY }"),
        ("if_statement", "if $$$COND { $$$BODY }"),
        ("for_statement", "for $$$COND { $$$BODY }"),
        ("switch_statement", "switch $$$COND { $$$BODY }"),
        ("select_statement", "select { $$$BODY }"),
    ],
    "typescript": [
        ("function_declaration", "function $FUNC($$$ARGS) { $$$BODY }"),
        ("method_definition", "$FUNC($$$ARGS) { $$$BODY }"),
        ("if_statement", "if ($COND) { $$$BODY }"),
        ("for_statement", "for ($$$INIT) { $$$BODY }"),
        ("for_in_statement", "for ($$$INIT) { $$$BODY }"),
        ("while_statement", "while ($COND) { $$$BODY }"),
        ("try_statement", "try { $$$BODY }"),
        ("switch_statement", "switch ($COND) { $$$BODY }"),
    ],
    "csharp": [
        ("method_declaration", "$$$MOD $TYPE $FUNC($$$ARGS) { $$$BODY }"),
        ("if_statement", "if ($COND) { $$$BODY }"),
        ("for_statement", "for ($$$INIT) { $$$BODY }"),
        ("foreach_statement", "foreach ($$$INIT) { $$$BODY }"),
        ("while_statement", "while ($COND) { $$$BODY }"),
        ("try_statement", "try { $$$BODY }"),
        ("switch_statement", "switch ($COND) { $$$BODY }"),
    ],
    "rust": [
        ("function_item", "fn $FUNC($$$ARGS) $$$RET { $$$BODY }"),
        ("if_expression", "if $COND { $$$BODY }"),
        ("for_expression", "for $VAR in $ITER { $$$BODY }"),
        ("while_expression", "while $COND { $$$BODY }"),
        ("match_expression", "match $EXPR { $$$BODY }"),
    ],
    "kotlin": [
        ("function_declaration", "fun $FUNC($$$ARGS) $$$RET { $$$BODY }"),
        ("if_expression", "if ($COND) { $$$BODY }"),
        ("for_statement", "for ($$$INIT) { $$$BODY }"),
        ("while_statement", "while ($COND) { $$$BODY }"),
        ("try_expression", "try { $$$BODY }"),
        ("when_expression", "when ($$$COND) { $$$BODY }"),
    ],
    "java": [
        ("method_declaration", "$$$MOD $TYPE $FUNC($$$ARGS) { $$$BODY }"),
        ("if_statement", "if ($COND) { $$$BODY }"),
        ("for_statement", "for ($$$INIT) { $$$BODY }"),
        ("enhanced_for_statement", "for ($$$INIT) { $$$BODY }"),
        ("while_statement", "while ($COND) { $$$BODY }"),
        ("try_statement", "try { $$$BODY }"),
        ("switch_expression", "switch ($COND) { $$$BODY }"),
    ],
}
PATTERNS["javascript"] = PATTERNS["typescript"]
PATTERNS["tsx"] = PATTERNS["typescript"]
PATTERNS["jsx"] = PATTERNS["typescript"]

LANG_BY_EXT = {
    "py": "python",
    "go": "go",
    "ts": "typescript", "tsx": "tsx",
    "js": "javascript", "jsx": "jsx",
    "cs": "csharp",
    "rs": "rust",
    "kt": "kotlin", "kts": "kotlin",
    "java": "java",
}

KEYWORDS = frozenset("""
False None True and as assert async await break class continue def del elif else
except finally for from global if import in is lambda nonlocal not or pass raise
return try while with yield
func var const let type struct interface package import range defer go select case
default switch fallthrough map chan
function new delete typeof instanceof void this super extends implements
abstract boolean byte char double enum final float int long native short
static synchronized throws transient volatile
fn pub mod use crate self Self impl trait where loop match unsafe extern ref mut
val fun object companion when sealed data inner open override internal expect actual
""".split())


def normalize(text):
    lines = text.split("\n")
    if len(lines) > 1:
        indents = [len(l) - len(l.lstrip()) for l in lines[1:] if l.strip()]
        min_indent = min(indents) if indents else 0
        lines = [lines[0]] + [l[min_indent:] if len(l) >= min_indent else l for l in lines[1:]]
    text = "\n".join(lines)

    text = re.sub(r'"""[\s\S]*?"""', '"$STR"', text)
    text = re.sub(r"'''[\s\S]*?'''", "'$STR'", text)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '"$STR"', text)
    text = re.sub(r"'(?:[^'\\]|\\.)*'", "'$STR'", text)
    text = re.sub(r'`(?:[^`\\]|\\.)*`', '`$STR`', text)

    text = re.sub(r'\b0[xX][0-9a-fA-F]+\b', '$INT', text)
    text = re.sub(r'\b\d+\.\d+\b', '$FLOAT', text)
    text = re.sub(r'\b\d+\b', '$INT', text)

    var_map = {}
    counter = [0]

    def replace_ident(m):
        name = m.group(0)
        if name in KEYWORDS:
            return name
        if name.startswith("$"):
            return name
        if name not in var_map:
            counter[0] += 1
            var_map[name] = f"$V{counter[0]}"
        return var_map[name]

    text = re.sub(r'\b[a-zA-Z_]\w*\b', replace_ident, text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


def sloc_count(text):
    return sum(
        1 for l in text.split("\n")
        if l.strip()
        and not l.strip().startswith("#")
        and not l.strip().startswith("//")
        and not l.strip().startswith("/*")
        and not l.strip().startswith("*")
    )


def extract_blocks(repo_path, files, lang, min_lines):
    if lang not in PATTERNS:
        return []
    blocks = []
    for node_type, pattern in PATTERNS[lang]:
        try:
            result = subprocess.run(
                ["ast-grep", "run", "-p", pattern, "-l", lang, "--json"] + files,
                capture_output=True, text=True, cwd=repo_path, timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                continue
            data = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            continue

        for m in data:
            text = m.get("text", "")
            sloc = sloc_count(text)
            if sloc < min_lines:
                continue
            norm = normalize(text)
            h = hashlib.md5(norm.encode(), usedforsecurity=False).hexdigest()[:12]
            lines = text.split("\n")
            blocks.append({
                "file": m.get("file", ""),
                "start": m["range"]["start"]["line"],
                "end": m["range"]["end"]["line"],
                "node_type": node_type,
                "lang": lang,
                "hash": h,
                "sloc": sloc,
                "text": text,
                "text_preview": lines[0].strip()[:80],
            })
    return blocks


FUNC_KW = {
    "python": "def", "go": "func", "typescript": "function",
    "javascript": "function", "rust": "fn", "kotlin": "fun",
    "java": "private", "csharp": "private",
}


def suggest_helper(members, lang):
    if len(members) < 2:
        return None
    ident_re = re.compile(r'[a-zA-Z_]\w*')
    tokens_a = ident_re.findall(members[0]["text"])
    tokens_b = ident_re.findall(members[1]["text"])
    if len(tokens_a) != len(tokens_b):
        return None
    params = []
    seen = set()
    for ta, tb in zip(tokens_a, tokens_b):
        if ta != tb and ta not in KEYWORDS and tb not in KEYWORDS:
            if ta not in seen:
                params.append(ta)
                seen.add(ta)
    kw = FUNC_KW.get(lang, "function")
    node = members[0]["node_type"]
    is_func = "function" in node or "method" in node
    if not params:
        return f"{kw} extracted_helper() — identical copies, no parameters needed"
    if is_func:
        name = params[0]
        params = params[1:]
    else:
        name = "extracted_helper"
    if not params:
        return f"{kw} {name}() — only the name varies"
    param_str = ", ".join(params[:8])
    if len(params) > 8:
        param_str += ", ..."
    return f"{kw} {name}({param_str})"


def find_clones(blocks):
    groups = defaultdict(list)
    for b in blocks:
        groups[b["hash"]].append(b)

    clones = []
    clone_lines = set()
    for h, members in groups.items():
        if len(members) < 2:
            continue
        files = set(m["file"] for m in members)
        scope = "intra-file" if len(files) == 1 else "cross-file"
        suggestion = suggest_helper(members, members[0].get("lang", ""))
        clone = {
            "hash": h,
            "node_type": members[0]["node_type"],
            "instances": len(members),
            "scope": scope,
            "sloc": members[0]["sloc"],
            "locations": [
                (m["file"], m["start"], m["end"], m["text_preview"])
                for m in members
            ],
        }
        if suggestion:
            clone["suggestion"] = suggestion
        clones.append(clone)
        for m in members:
            for line in range(m["start"], m["end"] + 1):
                clone_lines.add((m["file"], line))
    return clones, len(clone_lines)


def main():
    p = argparse.ArgumentParser(
        description="Detect code clones via ast-grep normalization + hashing."
    )
    p.add_argument("--repo", default=".", help="Repository root")
    p.add_argument("--lang", help="Language (auto-detected from extensions if omitted)")
    p.add_argument("--min-lines", type=int, default=5,
                   help="Minimum SLOC for a block to be considered (default: 5)")
    p.add_argument("--json-output", action="store_true",
                   help="Output results as JSON")
    p.add_argument("files", nargs="+", help="Files to scan")
    args = p.parse_args()

    by_lang = defaultdict(list)
    for f in args.files:
        if args.lang:
            by_lang[args.lang].append(f)
        else:
            ext = f.rsplit(".", 1)[-1] if "." in f else ""
            lang = LANG_BY_EXT.get(ext)
            if lang:
                by_lang[lang].append(f)

    if not by_lang:
        print("DUP SKIPPED: no files with supported extensions")
        sys.exit(0)

    all_blocks = []
    for lang, lang_files in by_lang.items():
        all_blocks.extend(extract_blocks(args.repo, lang_files, lang, args.min_lines))

    clones, total_clone_lines = find_clones(all_blocks)

    if args.json_output:
        json.dump({
            "files_scanned": len(set(b["file"] for b in all_blocks)),
            "blocks_extracted": len(all_blocks),
            "clone_groups": len(clones),
            "total_clone_lines": total_clone_lines,
            "clones": clones,
        }, sys.stdout, indent=2)
        print()
        return

    files_scanned = len(set(b["file"] for b in all_blocks))
    print(f"Files: {files_scanned}")
    print(f"Blocks extracted: {len(all_blocks)}")
    print(f"Clone groups: {len(clones)}")
    print(f"Total cloned lines: {total_clone_lines}")

    intra = [c for c in clones if c["scope"] == "intra-file"]
    cross = [c for c in clones if c["scope"] == "cross-file"]
    print(f"  Intra-file groups: {len(intra)}")
    print(f"  Cross-file groups: {len(cross)}")
    print()

    for c in sorted(clones, key=lambda x: -x["instances"] * x["sloc"]):
        print(f"  [{c['scope']}] {c['node_type']} x{c['instances']} ({c['sloc']} SLOC) hash={c['hash']}")
        for f, s, e, preview in c["locations"]:
            print(f"    {f}:{s}-{e}  {preview}")
        if "suggestion" in c:
            print(f"    Suggestion: {c['suggestion']}")
        print()


if __name__ == "__main__":
    main()
