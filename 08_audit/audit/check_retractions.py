#!/usr/bin/env python3
"""
Retraction ledger v5 -- Markdown logical-block parser implementing the association contract.

VERSION HISTORY (every defect found by the reviewer, none by the lead):
  v1   generic prose tokens as allow-labels                                   REJECTED
  v2   shared structured markers within a window (one retraction licensed another) REJECTED
  v3   per-tag markers, FORWARD+backward window (later marker licensed earlier)    REJECTED
  v3.1 backward-only window (an earlier marker still licensed a later claim)       REJECTED
  v4   same-line containment (missed split claims F10; one marker suppressed two
       claims on a line; rejected the valid F03 grammar)                           REJECTED
  v5   CURRENT. Logical-block parse + declared normalization + one-node binding.

ASSOCIATION CONTRACT (review fixture suite, 2026-08-22 16:23):
  * A marker carries authority ONLY at the start of a Markdown BLOCKQUOTE claim capsule.
    Markers in paragraphs, tables, code fences, and Python source are inert (F08, F13).
  * A marker binds EXACTLY ONE claim node: the one exact lexical occurrence after it on
    its own line, else one exact occurrence on the IMMEDIATELY following line at the same
    blockquote depth (F02, F03). It never reaches further (F04) or backwards (F05).
  * Authoring grammar is deliberately narrow. A capsule is either
        > [RETRACTED:TAG] one exact historical literal
    or
        > [RETRACTED:TAG] reason:
        > one exact historical literal
    The marker must be the first body token. It binds at most one matching occurrence on
    that physical line, or one matching occurrence on the immediately following same-depth
    line in the pair form. Any later marker-like text is inert, and a target may not span
    capsule lines. Markers after a list bullet, HTML/comment text, or live claim are inert.
    Markdown punctuation after an authorized marker is literal target text, not a separate
    container. Claims outside capsules are still matched across logical Markdown blocks and
    are caught (F10, F17).
  * Code fences and tables are NOT retraction containers: claims inside them are caught
    (F11, F12).
  * Fail closed: anything the grammar does not explicitly authorize is reported.

NOT closable by this scheme, by construction:
  F16 paraphrase / semantic equivalence -> manual review, never a marker pass.
  F18 scan scope -> declared boundary; see SCAN MANIFEST and SCAN_SCOPE_POLICY.md below.

Bounded claim-cluster variants are different from F16. A ledger tag may enumerate a
small set of lexical formulations of the same already-retracted assertion. This catches
known restatements in any scanned file, but is not semantic equivalence or a claim that
arbitrary paraphrases are covered.

Usage:
    python3 research/audit/check_retractions.py             # scan
    python3 research/audit/check_retractions.py --selftest  # F01-F15, F17, F19 per ledger tag
"""
import os
import re
import shutil
import sys
import tempfile
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # research/
SELF = os.path.abspath(__file__)
MARKER_FMT = "[RETRACTED:{tag}]"
MARKER_RE = re.compile(r"^\[RETRACTED:([^\]\s]+)\](?=\s|$)")
QUOTE_RE = re.compile(r"^[ \t]{0,3}(?P<prefix>(?:>\s*)+)(?P<body>.*)$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")

# ---- SCAN MANIFEST (F18: declared scope; see audit/SCAN_SCOPE_POLICY.md) ---
SCAN_EXT = (".md", ".py")
EXCLUDE_DIRS = {"raw", "02_experiments", "03_result"}

LEDGER = [
    ("C0-01/E0", r"dimensionless number 1",
     "the omitted energy reference E0 CARRIES energy units",
     "the scale was silently set to the dimensionless number 1."),
    ("C0-02", r"only unbalanced can produce Category C",
     "slack CAN produce Category C at finite penalty weight",
     "only unbalanced can produce Category C by construction."),
    ("U16-01a", r"mechanically inflates",
     "a local gap sign does NOT determine a global C-rate",
     "R2 mechanically inflates the C-rate."),
    ("U16-01b", r"decides the C-rate|raises the B-rate",
     "local penalty signs only DIRECTIONALLY bias; rates need the experiment",
     "the infeasible-side sign decides the C-rate."),
    ("U16-03", r"U-16 and U-18 are one decision",
     "mathematically coupled, NOT one governance decision",
     "U-16 and U-18 are one decision."),
    ("U18b-1", r"exactly one nonzero root",
     "AT MOST one POSITIVE nonzero root; none when s <= c*a^2/2",
     "D has exactly one nonzero root regardless of c."),
    ("U18b-2", r"no fairness justification whatever|cannot improve comparative neutrality at all",
     "c cannot create a SECOND match, but it DOES move the single match location",
     "there is no fairness justification whatever for per-constraint c_j."),
    ("U18a-1", r"[Aa]ll matching-type reductions",
     "fixed-positive r covers target-point and fixed-weighted-mean matching ONLY",
     "All matching-type reductions are one family."),
    ("U18a-2", r"worst available option",
     "R1 lacks a stable matching interpretation; no ranking metric is defined",
     "R1 is the worst available option for rank stability."),
    ("U15-1", r"not absorbed across families or across encodings",
     "defensible only at FIXED numerical s and a; absorbability is U-18(a)",
     "it is not absorbed across families or across encodings."),
    ("U15-2", r"same (class of )?defect as C0-01|same defect class as C0-01"
              r"|only because.{0,160}native (?:violation|residual scale).{0,160}"
              r"(?:would )?fail.{0,120}fixed v_ref\s*=\s*1"
              r"|(?:would )?fail.{0,120}fixed v_ref\s*=\s*1.{0,160}only because"
              r".{0,160}native (?:violation|residual scale)",
     "A-as-one-dollar is dimensioned and invariant; reachability, not units, selects D005",
     "this is the same defect class as C0-01."),
    ("U15-5", r"v_budget.{0,20}=.{0,5}gcd\(prices\)",
     "v_budget is the EXACT DP-derived attainable minimum; gcd is only a lower bound",
     "with v_budget = gcd(prices) = 5."),
    ("U01", r"Decide jointly with U-16",
     "U-18(a) has no recommendation; U-18(b) is recommended only",
     "Decide jointly with U-16."),
    ("U18b-3", r"[Nn]o recommendation is offered for either part",
     "part (a) has NO recommendation; part (b) has the unapproved c_j = 1 recommendation",
     "No recommendation is offered for either part."),
]


# ---- F17: declared, bounded normalization ---------------------------------
PUNCT_TRANSLATION = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u00a0": " ", "\u2000": " ", "\u2001": " ", "\u2002": " ",
    "\u2003": " ", "\u2004": " ", "\u2005": " ", "\u2006": " ",
    "\u2007": " ", "\u2008": " ", "\u2009": " ", "\u200a": " ",
    "\u202f": " ", "\u205f": " ", "\u3000": " ",
})


def normalize(text):
    """Normalize visible Markdown text; semantic equivalence remains F16/manual review."""
    t = unicodedata.normalize("NFKC", text).translate(PUNCT_TRANSLATION)
    t = LINK_RE.sub(r"\1", t)
    # Preserve identifier underscores. Only paired visible-text delimiters are removed.
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"(\*{1,3})([^*]+?)\1", r"\2", t)
    t = re.sub(r"~~([^~]+)~~", r"\1", t)
    return re.sub(r"\s+", " ", t).strip().casefold()


NORMALIZED_LEDGER = [
    (tag, re.compile(normalize(pat)), correct, example)
    for tag, pat, correct, example in LEDGER
]


def quote_parts(raw):
    """Return (quote depth, body) for a Markdown blockquote line, else None."""
    match = QUOTE_RE.match(raw)
    if not match:
        return None
    return match.group("prefix").count(">"), match.group("body")


def matches(tag, text):
    """Return every nonoverlapping normalized lexical match for one ledger tag."""
    norm = normalize(text)
    return [m for entry_tag, pat, _, _ in NORMALIZED_LEDGER if entry_tag == tag for m in pat.finditer(norm)]


def has_match(tag, text):
    return bool(matches(tag, text))


def ledger_entry(tag):
    for entry_tag, _, correct, _ in LEDGER:
        if entry_tag == tag:
            return correct
    return None


# ---- logical-block parse ---------------------------------------------------
def parse_blocks(lines, is_py):
    """Yield (kind, [(lineno, raw_line)], quote_depth_or_none)."""
    if is_py:
        for i, line in enumerate(lines, 1):
            yield ("code", [(i, line)], None)
        return
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        if raw.lstrip().startswith("```"):
            buf = [(i + 1, raw)]
            i += 1
            while i < n and not lines[i].lstrip().startswith("```"):
                buf.append((i + 1, lines[i]))
                i += 1
            if i < n:
                buf.append((i + 1, lines[i]))
                i += 1
            yield ("fence", buf, None)
            continue
        quote = quote_parts(raw)
        if quote:
            depth = quote[0]
            buf = []
            while i < n:
                candidate = quote_parts(lines[i])
                if not candidate or candidate[0] != depth:
                    break
                buf.append((i + 1, lines[i]))
                i += 1
            yield ("quote", buf, depth)
            continue
        if raw.lstrip().startswith("|"):
            buf = []
            while i < n and lines[i].lstrip().startswith("|"):
                buf.append((i + 1, lines[i]))
                i += 1
            yield ("table", buf, None)
            continue
        if not raw.strip():
            i += 1
            continue
        buf = []
        while i < n and lines[i].strip() and not lines[i].lstrip().startswith(("```", ">", "|")):
            buf.append((i + 1, lines[i]))
            i += 1
        yield ("para", buf, None)


def add_hit(out, rel, lineno, tag, text):
    out.append((rel, lineno, tag, normalize(text)[:100], ledger_entry(tag)))


def add_orphan_marker(out, rel, lineno, tag, text, reason):
    """Report a syntactically authoritative marker that bound no ledger claim."""
    out.append((rel, lineno, "F19", normalize(text)[:100],
                f"retraction marker [{tag}] {reason}"))


def scan_quote_block(out, rel, buf):
    """Scan a quote block. Only exact inline/pair capsules authorize a physical line."""
    lines = []
    for lineno, raw in buf:
        depth, body = quote_parts(raw)
        lines.append((lineno, depth, body))

    consumed = set()  # (tag, line_index); valid capsules always contain exactly one match.
    for index, (lineno, depth, body) in enumerate(lines):
        marker = MARKER_RE.match(body)
        if not marker:
            continue
        tag = marker.group(1)
        if ledger_entry(tag) is None:
            add_orphan_marker(out, rel, lineno, tag, body, "has an unknown tag")
            continue
        suffix = body[marker.end():]
        own_matches = matches(tag, suffix)
        if len(own_matches) == 1:
            consumed.add((tag, index))
            continue
        # Pair capsule: marker line has no target, ends in colon, and consumes only
        # the immediately following physical line at the same quote depth.
        if own_matches or not normalize(suffix).endswith(":") or index + 1 >= len(lines):
            add_orphan_marker(out, rel, lineno, tag, body,
                              "does not bind exactly one claim in its allowed node")
            continue
        _, next_depth, next_body = lines[index + 1]
        if next_depth != depth or MARKER_RE.match(next_body) or len(matches(tag, next_body)) != 1:
            add_orphan_marker(out, rel, lineno, tag, body,
                              "does not bind exactly one claim in its allowed node")
            continue
        consumed.add((tag, index + 1))

    line_has_match = {tag: False for tag, _, _, _ in LEDGER}
    for index, (lineno, _, body) in enumerate(lines):
        for tag, _, _, _ in LEDGER:
            if not has_match(tag, body):
                continue
            line_has_match[tag] = True
            if (tag, index) not in consumed:
                add_hit(out, rel, lineno, tag, body)

    # Quote paragraphs also search across soft line breaks. Only add a cross-line hit
    # where no physical line contained the literal, avoiding a duplicate of a live line.
    joined = " ".join(body for _, _, body in lines)
    for tag, _, _, _ in LEDGER:
        if has_match(tag, joined) and not line_has_match[tag]:
            add_hit(out, rel, lines[0][0], tag, joined)


def scan(root):
    """Return (hits, files). hit = (relpath, lineno, tag, text, correct)."""
    out, files = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(SCAN_EXT):
                continue
            path = os.path.join(dirpath, fn)
            if os.path.abspath(path) == SELF:
                continue
            files += 1
            rel = os.path.relpath(path, root)
            lines = open(path, encoding="utf-8").read().splitlines()
            for kind, buf, _ in parse_blocks(lines, fn.endswith(".py")):
                if kind == "quote":
                    scan_quote_block(out, rel, buf)
                    continue
                if kind == "table":
                    nodes = [(lineno, cell) for lineno, raw in buf
                             for cell in raw.strip().strip("|").split("|")]
                elif kind == "fence":
                    nodes = [(buf[0][0], " ".join(raw for _, raw in buf[1:-1]))]
                elif kind == "para":
                    nodes = [(buf[0][0], " ".join(raw for _, raw in buf))]
                else:  # Python source is searchable, but never a marker authority.
                    nodes = buf
                for lineno, text in nodes:
                    for tag, _, _, _ in LEDGER:
                        if has_match(tag, text):
                            add_hit(out, rel, lineno, tag, text)
    return out, files


# ---- self-test: the agreed fixture contract --------------------------------
def _split_at_word(text):
    """Split a claim across two physical lines at a WORD boundary (review F10)."""
    mid = len(text) // 2
    cut = text.rfind(" ", 0, mid)
    cut = cut if cut > 0 else mid
    return f"{text[:cut]}\n{text[cut+1:]}\n"


def selftest():
    print("=" * 78); print("RETRACTION LEDGER SELF-TEST - review fixture contract F01-F15 + F17 + F19")
    print("=" * 78)
    bad, tmp, total_cases = [], tempfile.mkdtemp(), 0
    try:
        for tag, pat, correct, C in LEDGER:
            M = MARKER_FMT.format(tag=tag)
            OTHER = MARKER_FMT.format(tag="U18b-3" if tag != "U18b-3" else "U01")
            d = os.path.join(tmp, "c"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)

            def verdict(name, text):
                for stale in ("f.md", "f.py"):
                    candidate = os.path.join(d, stale)
                    if os.path.exists(candidate):
                        os.unlink(candidate)
                open(os.path.join(d, name), "w").write(text)
                return any(h[2] == tag for h in scan(d)[0])

            def v(text):
                return verdict("f.md", text)

            def v_py(text):
                return verdict("f.py", text)

            split_target = _split_at_word(C).strip().splitlines()
            if len(split_target) != 2:
                raise AssertionError("split fixture must have exactly two lines")

            cases = {
                "F01 live claim":            (v(f"{C}\n"), True),
                "F02 same-line marker":      (v(f"> {M} {C}\n"), False),
                "F03 immediate predecessor": (v(f"> {M} superseded wording:\n> {C}\n"), False),
                "F03 quote-depth boundary":  (v(f"> {M} superseded wording:\n>> {C}\n"), True),
                "F04 earlier-marker prox":   (v(f"> {M} old quote:\n> filler\n> filler\n> {C}\n"), True),
                "F05 later-marker prox":     (v(f"> {C}\n> filler\n> {M} old quote\n"), True),
                "F06 different-tag marker":  (v(f"> {OTHER} old quote\n> {C}\n"), True),
                "F07 marker in prior block": (v(f"> {M} old quote\n\n{C}\n"), True),
                "F08 marker as example":     (v(f"Example syntax: {M}\n{C}\n"), True),
                "F08 quote marker as example": (v(f"> Example syntax: {M}\n> {C}\n"), True),
                "F08 Python marker inert":    (v_py(f'x = "{M} {C}"\n'), True),
                "F08 lowercase marker inert":  (v(f"> {M.lower()} {C}\n"), True),
                "F08 mixed-case marker inert": (v(f"> {M.replace('RETRACTED', 'Retracted')} {C}\n"), True),
                "F08 Unicode tag marker inert": (v(f"> {M.replace(':', ':' + chr(0x2011), 1)} {C}\n"), True),
                "F08 HTML marker inert":       (v(f"> <!-- {M} --> {C}\n"), True),
                "F09 split marker":          (v(f"> [RETRACTED:\n> {tag}]\n> {C}\n"), True),
                "F10 claim split over lines":(v(_split_at_word(C)), True),
                "F11 claim in table cell":   (v(f"| note | {C} |\n"), True),
                "F12 claim in code fence":   (v(f"```text\n{C}\n```\n"), True),
                "F13 marker in code fence":  (v(f"```text\n{M}\n```\n{C}\n"), True),
                "F14 one marker two claims": (v(f"> {M} {C} Live: {C}\n"), True),
                "F14 semicolon second claim": (v(f"> {M} {C}; Live: {C}\n"), True),
                "F14 two markers two claims":  (v(f"> {M} {C} {M} {C}\n"), True),
                "F15 marker after live claim": (v(f"> {C} {M}\n"), True),
                "F15 marker after bullet":     (v(f"> - {M} {C}\n"), True),
                "F15 split capsule target":    (v(f"> {M} {split_target[0]}\n> {split_target[1]}\n"), True),
                "F15 NL negation no marker": (v(f"> Do not say {C}\n"), True),
                "F17 normalization (dashes/emphasis)":
                                             (v(f"*{C.replace('-', chr(0x2014))}*\n"), True),
                "F17 case-folding":          (v(C.upper() + "\n"), True),
                "F17 link label":            (v(C.replace("only", "[only](https://example.test)", 1) + "\n"), True),
            }
            if tag == "U15-2":
                # P1: an equivalent claim reappeared in a different file with none of
                # the original "same defect class" vocabulary. This is a finite,
                # documented claim-cluster variant, not an attempt at F16 semantics.
                P1 = ("This holds only because D005 defines v_j as a native violation; "
                      "it would fail under a fixed v_ref = 1.")
                cases.update({
                    "F17 U15-2 claim-cluster restatement other file":
                        (verdict("elsewhere.md", P1 + "\n"), True),
                    "F17 U15-2 claim-cluster capsule other file":
                        (verdict("elsewhere.md", f"> {M} {P1}\n"), False),
                    "F17 U15-2 correct dimensional contrast":
                        (v("Option A as one currency unit is invariant; D005 is selected for reachability.\n"), False),
                })
            total_cases += len(cases)
            fails = [k for k, (got, want) in cases.items() if got != want]
            if fails:
                bad.append(f"{tag}: {', '.join(fails)}")
            print(f"  [{'OK ' if not fails else 'FAIL'}] {tag:<10} "
                  f"{len(cases)-len(fails)}/{len(cases)} fixtures"
                  + (f"  failing: {fails}" if fails else ""))

        # F19 is scoped to markers in the authoritative position of a
        # blockquote capsule. Paragraph/code examples remain inert per F08.
        tag, _, _, C = LEDGER[0]
        M = MARKER_FMT.format(tag=tag)
        def f19_verdict(name, text):
            for stale in ("f.md", "f.py"):
                candidate = os.path.join(d, stale)
                if os.path.exists(candidate):
                    os.unlink(candidate)
            open(os.path.join(d, name), "w").write(text)
            return any(h[2] == "F19" for h in scan(d)[0])

        f19_cases = {
            "F19 valid inline marker": (f19_verdict("f.md", f"> {M} {C}\n"), False),
            "F19 valid pair marker": (f19_verdict("f.md", f"> {M} reason:\n> {C}\n"), False),
            "F19 marker without target": (f19_verdict("f.md", f"> {M} historical wording\n"), True),
            "F19 pair marker with nonmatching target":
                (f19_verdict("f.md", f"> {M} reason:\n> unrelated wording\n"), True),
            "F19 unknown marker tag":
                (f19_verdict("f.md", f"> [RETRACTED:UNKNOWN] {C}\n"), True),
            "F19 depth-mismatched target": (f19_verdict("f.md", f"> {M} reason:\n>> {C}\n"), True),
            "F19 marker in paragraph remains inert":
                (f19_verdict("f.md", f"{M} historical wording\n"), False),
            "F19 marker in Python remains inert":
                (f19_verdict("f.py", f'x = "{M} historical wording"\n'), False),
        }
        total_cases += len(f19_cases)
        f19_fails = [k for k, (got, want) in f19_cases.items() if got != want]
        if f19_fails:
            bad.append("F19: " + ", ".join(f19_fails))
        print(f"  [{'OK ' if not f19_fails else 'FAIL'}] {'F19':<10} "
              f"{len(f19_cases)-len(f19_fails)}/{len(f19_cases)} fixtures"
              + (f"  failing: {f19_fails}" if f19_fails else ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 78)
    if bad:
        print(f"RESULT: SELF-TEST FAILED ({len(bad)} tag(s))")
        for b in bad:
            print("  - " + b)
        return 1
    print(f"RESULT: SELF-TEST PASSED - {len(LEDGER)} tags, {total_cases} fixture assertions")
    print("  NOT covered by construction: F16 paraphrase (manual review)")
    print("  F18: declared scan boundary; see audit/SCAN_SCOPE_POLICY.md")
    print("=" * 78)
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    fails, files = scan(ROOT)
    print("=" * 78); print("RETRACTION LEDGER CHECK (v5, logical-block grammar)"); print("=" * 78)
    print(f"  {len(LEDGER)} enumerated claims, {files} files scanned under research/")
    print(f"  MANIFEST: ext {SCAN_EXT}, excluding {sorted(EXCLUDE_DIRS)} and this file")
    if fails:
        print(f"\n  {len(fails)} UNAUTHORIZED OCCURRENCE(S):\n")
        for rel, i, tag, txt, correct in fails:
            print(f"  FAIL [{tag}] {rel}:{i}\n        found  : {txt}\n        correct: {correct}\n")
        print("=" * 78); print("RESULT: FAILED"); return 1
    print("\n  No enumerated claim occurs outside the declared retraction grammar.")
    print("  LIMIT: enumerated literals only; paraphrase / semantic equivalence (F16) is")
    print("         NOT established by this pass.")
    print("  SCOPE (F18): the declared research/ manifest is intentional; append-only logs and")
    print("              automated messages are out of scope by policy (audit/SCAN_SCOPE_POLICY.md).")
    print("=" * 78); print("RESULT: PASS"); print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
