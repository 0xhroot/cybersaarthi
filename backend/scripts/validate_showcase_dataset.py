"""Static validator for the synthetic SIH showcase dataset.

Checks ``dataset_manifest.json`` against every fixture file: required fields,
referential integrity, date consistency, transaction arithmetic, entity
relationships, source references, the designed contradictions, the designed
report-audit defects, and fixture isolation (no real data).

Static and stdlib-only — no database, no API, no model. Runtime state is
checked separately by ``make demo-status`` (see docs/demo/SIH_SHOWCASE.md).

Run:
    python -m scripts.validate_showcase_dataset            # from backend/
    python3 backend/scripts/validate_showcase_dataset.py   # from repo root

Exit codes: 0 = all checks pass, 1 = at least one failure, 2 = setup error.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "dataset_manifest.json"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DM_DATE = re.compile(r"^\d{2}/\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@([\w-]+\.[\w.-]+)\b")
CASE_NO_RE = re.compile(r"\b([A-Z][A-Z0-9]*-\d{4}-\d{2,4})\b")
PERSON_LINE = re.compile(
    r"^(?P<a>[A-Z][A-Za-z'’-]+ [A-Z][A-Za-z'’-]+) .+? "
    r"(?P<b>[A-Z][A-Za-z'’-]+ [A-Z][A-Za-z'’-]+) on (?P<d>\d{2}/\d{2}) "
    r"near (?P<city>[A-Za-z' ]+?)\.?$"
)
CDR_LINE = re.compile(r"^Call detail records show device (?P<ph>\+91-\d{10})")

# The dataset's fixed fictional window (all fixtures live inside it).
MIN_DATE = date(2026, 1, 1)
MAX_DATE = date(2026, 12, 31)


class Reporter:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passed = 0

    def check(self, ok: bool, label: str) -> bool:
        if ok:
            self.passed += 1
        else:
            self.failures.append(label)
        return ok


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_iso(value: str) -> date | None:
    if not ISO_DATE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def money(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def norm_phone(value: str) -> str:
    return re.sub(r"[^\d+]", "", value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="only print failures + summary")
    args = ap.parse_args()

    if not MANIFEST_PATH.is_file():
        print(f"FATAL: manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rep = Reporter()

    fixtures = {f["path"]: f for f in manifest["fixtures"]}
    files = sorted(
        str(p.relative_to(HERE))
        for p in HERE.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix in {".txt", ".csv", ".json", ".md"}
        and p.name not in {"dataset_manifest.json", "validate_showcase_dataset.py"}
    )

    # 0. coverage: every fixture file is declared, every declared file exists.
    declared = set(fixtures)
    on_disk = {f for f in files if not f.endswith(".py")}
    rep.check(
        declared == on_disk,
        f"manifest coverage: undeclared={sorted(on_disk - declared)} "
        f"missing={sorted(declared - on_disk)}",
    )
    if not args.quiet:
        print(f"== manifest: {len(fixtures)} fixtures declared, {len(on_disk)} on disk ==")

    def rel(path: str) -> Path:
        return HERE / path

    def spec(path: str) -> dict:
        return fixtures[path]

    STMT = "showcase_fixtures/merchant_statement.csv"
    LEDGER = "showcase_fixtures/wallet_ledger.json"

    # ------------------------------------------------------------------
    # 1. Required fields (CSV columns / JSON item keys / non-empty text)
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 1. required fields ==")
    rows_by_path: dict[str, list[dict[str, str]]] = {}
    for path, fx in fixtures.items():
        p = rel(path)
        if not rep.check(p.is_file(), f"{path}: file exists"):
            continue
        text = p.read_text(encoding="utf-8")
        rep.check(bool(text.strip()), f"{path}: non-empty")
        if fx.get("format") == "csv":
            rows = load_csv(p)
            rows_by_path[path] = rows
            header = list(rows[0].keys()) if rows else []
            missing = [c for c in fx.get("required_columns", []) if c not in header]
            rep.check(not missing, f"{path}: missing columns {missing}")
            rep.check(bool(rows), f"{path}: has rows")
            if not args.quiet:
                print(f"  {path}: {len(rows)} rows, columns ok={not missing}")
        elif fx.get("format") == "json":
            data = json.loads(text)
            rep.check(isinstance(data, list) and bool(data), f"{path}: non-empty list")
            if isinstance(data, list) and data:
                missing = [k for k in fx.get("item_keys", []) if k not in data[0]]
                rep.check(not missing, f"{path}: item keys missing {missing}")
            if not args.quiet:
                print(f"  {path}: {len(data) if isinstance(data, list) else '?'} items")

    # ------------------------------------------------------------------
    # 2. Date consistency
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 2. date consistency ==")
    statement = rows_by_path.get("showcase_fixtures/merchant_statement.csv", [])
    dated: list[date] = []
    for row in statement:
        d = row["date"]
        if d == "":
            continue  # TXN-SIH-1007: designed gap
        parsed = parse_iso(d)
        if not rep.check(
            parsed is not None, f"statement: {row['transaction_id']} date {d!r} parses"
        ):
            continue
        assert parsed is not None
        rep.check(MIN_DATE <= parsed <= MAX_DATE, f"statement: {d} inside fictional window")
        dated.append(parsed)
    rep.check(dated == sorted(dated), "statement: dated rows chronological")

    ledger = json.loads(rel("showcase_fixtures/wallet_ledger.json").read_text(encoding="utf-8"))
    for item in ledger:
        rep.check(
            parse_iso(item["date"]) is not None, f"ledger: {item['transaction_id']} date parses"
        )

    transfers = json.loads(rel("sih_demo_seed/transfers.json").read_text(encoding="utf-8"))
    bad_dates = [t for t in transfers if parse_iso(t.get("date", "")) is None]
    rep.check(not bad_dates, f"transfers: {len(bad_dates)} unparseable dates")

    er = rows_by_path.get("showcase_fixtures/entity_review.csv", [])
    for row in er:
        rep.check(
            parse_iso(row["incident_date"]) is not None,
            f"entity_review: incident_date {row['incident_date']!r} parses",
        )

    sp = rows_by_path.get("showcase_fixtures/supporting_payments.csv", [])
    for row in sp:
        rep.check(
            parse_iso(row["date"]) is not None,
            f"supporting_payments: {row['reference']} date parses",
        )

    if not args.quiet:
        print(
            f"  statement: {len(dated)} dated rows in order; transfers: {len(transfers)} dates ok"
        )

    # ------------------------------------------------------------------
    # 3. Transaction arithmetic
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 3. transaction arithmetic ==")
    amounts = [money(r["amount"]) for r in statement]
    rep.check(
        all(a is not None and a > 0 for a in amounts), "statement: all amounts positive decimals"
    )
    dated_rows = [r for r in statement if r["date"] != "" and r["status"] == "completed"]
    dated_total = sum((money(r["amount"]) or Decimal(0)) for r in dated_rows)
    all_total = sum((money(r["amount"]) or Decimal(0)) for r in statement)
    exp_dated = Decimal(spec(STMT)["expected"]["dated_completed_total"])
    exp_all = Decimal(spec(STMT)["expected"]["all_rows_total"])
    rep.check(len(dated_rows) == 6, f"statement: 6 dated completed rows (got {len(dated_rows)})")
    rep.check(dated_total == exp_dated, f"statement: dated total {dated_total} == {exp_dated}")
    rep.check(all_total == exp_all, f"statement: all-rows total {all_total} == {exp_all}")
    if not args.quiet:
        print(
            f"  6 dated completed = {dated_total} (report claim 3); "
            f"7 rows = {all_total} (report claim: 125000.00 → mismatch by design)"
        )

    stmt_by_txn = {r["transaction_id"]: money(r["amount"]) for r in statement}
    led_by_txn = {i["transaction_id"]: money(i["amount"]) for i in ledger}
    pair = spec(LEDGER)["expected"]["designed_contradiction"]
    delta = (stmt_by_txn[pair["transaction_id"]] or 0) - (led_by_txn[pair["transaction_id"]] or 0)
    rep.check(
        delta == Decimal(pair["delta"]),
        f"ledger: designed contradiction {pair['transaction_id']} delta {delta} == {pair['delta']}",
    )

    rep.check(
        len(transfers) == spec("sih_demo_seed/transfers.json")["expected"]["rows"],
        f"transfers: row count {len(transfers)} == manifest",
    )
    rep.check(
        all(isinstance(t.get("amount"), int) and t["amount"] >= 1 for t in transfers),
        "transfers: amounts are positive integers",
    )
    rep.check(
        all(t.get("from_account") and t.get("to_account") for t in transfers),
        "transfers: every row has both endpoints",
    )

    # ------------------------------------------------------------------
    # 4. Entity relationships
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 4. entity relationships ==")

    def find(name: str) -> dict[str, str] | None:
        return next((r for r in er if r["name"] == name), None)

    for a, b in spec("showcase_fixtures/entity_review.csv")["expected"]["alias_pairs"]:
        ra, rb = find(a), find(b)
        if rep.check(
            ra is not None and rb is not None, f"entity_review: alias pair {a!r}/{b!r} present"
        ):
            assert ra and rb
            rep.check(
                norm_phone(ra["phone"]) == norm_phone(rb["phone"]),
                f"entity_review: {a}/{b} share normalized phone",
            )
            rep.check(
                ra["incident_date"] == rb["incident_date"],
                f"entity_review: {a}/{b} share incident date",
            )

    primary_phones = {norm_phone(r["phone"]) for r in er}
    payout_a = next((r for r in sp if r["reference"] == "PAYOUT-A"), None)
    rep.check(
        payout_a is not None and norm_phone(payout_a["beneficiary_phone"]) in primary_phones,
        "supporting_payments: PAYOUT-A shares a phone with a primary-case entity",
    )
    payout_b = next((r for r in sp if r["reference"] == "PAYOUT-B"), None)
    rep.check(
        payout_b is not None and norm_phone(payout_b["beneficiary_phone"]) not in primary_phones,
        "supporting_payments: PAYOUT-B phone is distinct (merchant-name-only link)",
    )
    if not args.quiet:
        alias_pairs = spec("showcase_fixtures/entity_review.csv")["expected"]["alias_pairs"]
        print(
            f"  {len(alias_pairs)} alias pairs share phone+date; "
            "PAYOUT-A links cases, PAYOUT-B does not"
        )

    # ------------------------------------------------------------------
    # 5. Referential integrity (associations → persons)
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 5. referential integrity ==")
    persons = rows_by_path.get("sih_demo_seed/persons.csv", [])
    person_names = {r["name"] for r in persons}
    person_phones = {r["phone"] for r in persons}
    assoc = [
        ln.strip()
        for ln in rel("sih_demo_seed/associations.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    person_lines = cdr_lines = unparsed = 0
    unresolved: list[str] = []
    for line in assoc:
        if line.startswith("Call detail records"):
            cdr_lines += 1
            m = CDR_LINE.match(line)
            if not m or m.group("ph") not in person_phones:
                unresolved.append(line)
            continue
        m = PERSON_LINE.match(line)
        if not m:
            unparsed += 1
            unresolved.append(line)
            continue
        person_lines += 1
        if m.group("a") not in person_names or m.group("b") not in person_names:
            unresolved.append(line)
    exp = spec("sih_demo_seed/associations.txt")["expected"]
    rep.check(len(assoc) == exp["lines"], f"associations: {len(assoc)} lines == {exp['lines']}")
    rep.check(
        person_lines == exp["person_lines"],
        f"associations: {person_lines} person lines == {exp['person_lines']}",
    )
    rep.check(
        cdr_lines == exp["cdr_lines"], f"associations: {cdr_lines} CDR lines == {exp['cdr_lines']}"
    )
    rep.check(unparsed == 0, f"associations: {unparsed} lines failed the grammar")
    rep.check(
        not unresolved, f"associations: {len(unresolved)} unresolved refs e.g. {unresolved[:2]}"
    )
    rep.check(
        len(persons) == spec("sih_demo_seed/persons.csv")["expected"]["rows"],
        f"persons: {len(persons)} rows == manifest",
    )
    phone_pat = re.compile(spec("sih_demo_seed/persons.csv")["expected"]["phone_pattern"])
    bad_phones = [r["phone"] for r in persons if not phone_pat.match(r["phone"])]
    rep.check(
        not bad_phones,
        f"persons: {len(bad_phones)} phones outside synthetic pattern e.g. {bad_phones[:3]}",
    )
    rep.check(
        all(
            len(r["name"].split()) == spec("sih_demo_seed/persons.csv")["expected"]["name_words"]
            for r in persons
        ),
        "persons: every name has the expected word count",
    )
    if not args.quiet:
        print(
            f"  persons={len(persons)} assoc={person_lines}+{cdr_lines}cdr "
            f"unresolved={len(unresolved)}"
        )

    # ------------------------------------------------------------------
    # 6. Source references
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 6. source references ==")
    hm = rows_by_path.get("showcase_fixtures/hash_manifest.csv", [])
    exp_files = manifest["fixtures"][5]["expected"]["filenames"]
    rep.check([r["filename"] for r in hm] == exp_files, "hash_manifest: filenames match manifest")
    hashes = [r["sha256"] for r in hm]
    rep.check(
        all(SHA256_RE.match(h) for h in hashes), "hash_manifest: every sha256 is 64 hex chars"
    )
    rep.check(len(set(hashes)) == len(hashes), "hash_manifest: sha256 values unique")

    draft = rel("showcase_fixtures/report_draft.tpl.md").read_text(encoding="utf-8")
    exp_placeholders = set(manifest["fixtures"][6]["expected"]["placeholders"])
    found_placeholders = set(re.findall(r"\{\{[A-Z_]+\}\}", draft))
    rep.check(
        found_placeholders == exp_placeholders,
        f"report_draft: placeholders {sorted(found_placeholders)} == manifest",
    )
    rep.check(
        "{{EV_MISSING}}" in found_placeholders,
        "report_draft: designed dangling citation {{EV_MISSING}} still present",
    )

    complaint = rel("showcase_fixtures/complaint_mixed.txt").read_text(encoding="utf-8")
    cref = manifest["fixtures"][0]["expected"]["complaint_ref"]
    rep.check(cref in complaint, f"complaint: reference {cref} present")

    # ------------------------------------------------------------------
    # 7. Expected contradiction (the showcase's point)
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 7. expected contradictions ==")
    rep.check(
        delta == Decimal("2500.00"),
        f"contradiction: statement 47500.00 vs ledger 45000.00 (delta {delta})",
    )
    rep.check(
        "47,500.00" in complaint and "45,000.00" in complaint,
        "complaint: states both sides of the contradiction",
    )
    if not args.quiet:
        print("  TXN-SIH-1001: statement 47500.00 vs ledger 45000.00, delta 2500.00 ✓")

    # ------------------------------------------------------------------
    # 8. Expected report-audit findings (designed defects)
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 8. report-audit designed defects ==")
    defects = manifest["fixtures"][6]["expected"]["designed_defects"]
    claim6_wrong = "INR 15,300.00" in draft and "TXN-SIH-1002" in draft
    rep.check(claim6_wrong, f"report_draft defect present: {defects[0]}")
    rep.check(
        "INR 125,000.00" in draft and all_total != Decimal("125000.00"),
        f"report_draft defect present: {defects[1]}",
    )
    rep.check("{{EV_MISSING}}" in draft, f"report_draft defect present: {defects[2]}")
    claim8 = re.search(r"^8\. .*$", draft, re.M)
    rep.check(
        claim8 is not None and "evidence:" not in claim8.group(0),
        f"report_draft defect present: {defects[3]}",
    )
    rep.check(
        "2026-04-04" in draft and all(d != "2026-04-04" for d in (r["date"] for r in statement)),
        f"report_draft defect present: {defects[4]}",
    )
    # Positive controls: the two correct claims must stay correct.
    rep.check(
        "INR 125,700.00" in draft and dated_total == Decimal("125700.00"),
        "report_draft: correct claim 3 (125,700.00) matches statement arithmetic",
    )
    rep.check(
        "INR 2,500.00" in draft and delta == Decimal("2500.00"),
        "report_draft: correct claim 2 (2,500.00 discrepancy) matches arithmetic",
    )
    if not args.quiet:
        print(f"  {len(defects)} designed defects present; 2 correct claims verified as controls")

    # ------------------------------------------------------------------
    # 9. Fixture isolation (no real data)
    # ------------------------------------------------------------------
    if not args.quiet:
        print("\n== 9. fixture isolation ==")
    iso = manifest["isolation"]
    allowed_cases = set(iso["allowed_case_numbers"]) | set(iso.get("allowed_references", []))
    marker_re = re.compile(iso["marker"])
    iso_problems: list[str] = []
    for path in sorted(declared):
        text = rel(path).read_text(encoding="utf-8")
        for u in UUID_RE.findall(text):
            iso_problems.append(f"{path}: UUID {u}")
        for domain in EMAIL_RE.findall(text):
            if not domain.endswith(".test"):
                iso_problems.append(f"{path}: non-.test email domain {domain}")
        for case_no in CASE_NO_RE.findall(text):
            if case_no not in allowed_cases:
                iso_problems.append(f"{path}: unexpected case number {case_no}")
    rep.check(not iso_problems, f"isolation violations: {iso_problems[:5]}")

    # Synthetic markers on the free-text exhibits.
    for path in ("showcase_fixtures/complaint_mixed.txt", "showcase_fixtures/phishing_urls.txt"):
        rep.check(
            bool(marker_re.search(rel(path).read_text(encoding="utf-8"))),
            f"{path}: synthetic marker present",
        )

    # Inert URLs: .test TLD or private/literal hosts only — never reachable.
    url_lines = rel("showcase_fixtures/phishing_urls.txt").read_text(encoding="utf-8").splitlines()
    urls = [ln.strip() for ln in url_lines if ln.strip().startswith("http")]
    rep.check(
        len(urls) == manifest["fixtures"][4]["expected"]["urls"], f"phishing_urls: {len(urls)} URLs"
    )
    for u in urls:
        host = re.sub(r"^https?://", "", u).split("/")[0].split("@")[-1].split(":")[0]
        ok = host.endswith(".test") or host.startswith(("192.168.", "10.", "127."))
        rep.check(ok, f"phishing_urls: host {host} is inert (.test / private)")

    # No database dumps or model weights tracked by git (repo hygiene).
    try:
        import subprocess

        tracked = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(HERE.parent.parent), "ls-files"],  # noqa: S607 - fixed binary name
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout.splitlines()
        dumps = [f for f in tracked if f.endswith((".sql", ".dump", ".sqlite", ".db", ".gguf"))]
        rep.check(not dumps, f"git: no dumps/weights tracked e.g. {dumps[:3]}")
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pass

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    if rep.failures:
        print(f"FAIL: {len(rep.failures)} of {rep.passed + len(rep.failures)} checks failed")
        for f in rep.failures:
            print(f"  ✗ {f}")
        return 1
    print(
        f"OK: all {rep.passed} checks passed "
        f"({len(fixtures)} fixtures, {len(manifest['cases'])} cases, isolation clean)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
