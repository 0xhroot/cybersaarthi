"""Deterministic SIH demonstration evidence generator.

Generates three synthetic evidence files (CSV, JSON, TXT) that are uploaded and
ingested through the *real* CyberSaarthi HTTP pipeline during the SIH demo
rehearsal:

* persons.csv   -> person records (person+phone/vehicle/account/org/location)
* transfers.json -> account<->account money movement (TRANSFERRED_TO)
* associations.txt -> free-text co-occurrence (ASSOCIATED_WITH / VISITED)

Together these yield ~300-500 resolved entities with a rich, connected graph:
organisation-scoped communities, a central hub (high PageRank/betweenness), a
bridge node, a money-flow subgraph, geography links and closed loops for the
pattern detectors.

This module is deliberately free of any `app.` import: it only generates the
evidence payload bytes so the data enters through the real API pipeline.
All values are fabricated syntactic demo data (no real persons/identifiers).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

SIH_CASE_NUMBER = "SIH-2026-001"
RNG_SEED = 26189

PERSON_PREFIXES = (
    "Rajesh",
    "Aisha",
    "Vikram",
    "Priya",
    "Imran",
    "Deepa",
    "Rohan",
    "Meera",
    "Karan",
    "Sneha",
    "Arvind",
    "Ananya",
    "Farhan",
    "Divya",
    "Nikhil",
    "Pooja",
    "Sanjay",
    "Ritu",
    "Aditya",
    "Kavita",
    "Manoj",
    "Shalini",
    "Ravi",
    "Nisha",
    "Gaurav",
    "Tanvi",
    "Hari",
    "Asha",
)
SURNAMES = (
    "Sharma",
    "Mehta",
    "Patel",
    "Rao",
    "Iyer",
    "Singh",
    "Reddy",
    "Nair",
    "Gupta",
    "Das",
    "Joshi",
    "Khan",
    "Bose",
    "Menon",
    "Chopra",
    "Verma",
    "Pillai",
    "Agarwal",
)

ORGANIZATIONS = (
    "Nova Holding Ltd",
    "Vertex Infotech",
    "Bluepeak Exports",
    "Saffron Trading Co",
    "Orion Shipping",
    "Crimson Textiles",
    "Summit Logistics",
    "Eagle Freight",
    "Zephyr Agro",
    "Marina Oil Trading",
    "Delta Impex",
    "Phoenix Cargo",
)

CITIES = ("Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad", "Ahmedabad", "Jaipur")


@dataclass
class Person:
    name: str
    phone: str
    org: str
    city: str
    account: str | None = None
    vehicle: str | None = None
    tier: str = "member"


@dataclass
class Network:
    persons: list[Person] = field(default_factory=list)
    links: dict[str, set[str]] = field(default_factory=dict)


def _rng() -> random.Random:
    # Deterministic synthetic demo data, NOT cryptography. Seed fixed for
    # reproducible demonstrations. (S311 is a crypto-only warning.)
    return random.Random(RNG_SEED)  # noqa: S311


def _make_person(rng: random.Random, idx: int, org: str, city: str, tier: str = "member") -> Person:
    prefix = PERSON_PREFIXES[idx % len(PERSON_PREFIXES)]
    surname = SURNAMES[(idx * 7 + 3) % len(SURNAMES)]
    name = f"{prefix} {surname}"
    phone = f"+91-{9000000000 + (idx * 31) % 900000000}"
    account = f"AC-{1000 + idx}" if idx % 2 == 0 else None
    vehicle = f"MH01{idx:04d}AA" if idx % 3 == 0 else None
    return Person(
        name=name, phone=phone, org=org, city=city, account=account, vehicle=vehicle, tier=tier
    )


def build_network() -> Network:
    rng = _rng()
    net = Network()

    hub_a = Person(
        "Suresh Gupta",
        "+91-9000000001",
        "Nova Holding Ltd",
        "Mumbai",
        "AC-990001",
        "MH01BOSS01",
        "hub",
    )
    bridge = Person(
        "Vijay Singh", "+91-9000000002", "Vertex Infotech", "Delhi", "AC-990002", None, "bridge"
    )
    hub_b = Person(
        "Anita Nair", "+91-9000000003", "Bluepeak Exports", "Bengaluru", "AC-990003", None, "hub"
    )
    ring = [
        Person(
            "Ramesh Iyer", "+91-9000000004", "Nova Holding Ltd", "Mumbai", "AC-990004", None, "core"
        ),
        Person("Lata Devi", "+91-9000000005", "Nova Holding Ltd", "Mumbai", None, None, "core"),
        Person(
            "Omkar Joshi", "+91-9000000006", "Nova Holding Ltd", "Mumbai", "AC-990005", None, "core"
        ),
        Person("Nalini Das", "+91-9000000007", "Bluepeak Exports", "Bengaluru", None, None, "core"),
        Person(
            "Kunal Bose",
            "+91-9000000008",
            "Bluepeak Exports",
            "Bengaluru",
            "AC-990006",
            None,
            "core",
        ),
    ]
    net.persons = [hub_a, bridge, hub_b, *ring]

    next_idx = 100
    for org_i, org in enumerate(ORGANIZATIONS):
        city = CITIES[org_i % len(CITIES)]
        member_count = 8 + (org_i % 3)
        members = [_make_person(rng, next_idx + m, org, city) for m in range(member_count)]
        net.persons.extend(members)
        next_idx += member_count

    floaters: list[Person] = []
    for city in CITIES:
        for _ in range(3):
            org = ORGANIZATIONS[(next_idx + len(floaters)) % len(ORGANIZATIONS)]
            floaters.append(_make_person(rng, next_idx + len(floaters), org, city))
    net.persons.extend(floaters)

    def link(a: str, b: str) -> None:
        net.links.setdefault(a, set()).add(b)
        net.links.setdefault(b, set()).add(a)

    core_names = [p.name for p in ring]
    for i, a in enumerate(core_names):
        for b in core_names[i + 1 :]:
            link(a, b)
    for core in core_names:
        link(hub_a.name, core)

    link(bridge.name, hub_a.name)
    link(bridge.name, hub_b.name)
    link(hub_b.name, "Nalini Das")
    link(hub_b.name, "Kunal Bose")
    link("Nalini Das", "Kunal Bose")
    link("Omkar Joshi", "Lata Devi")

    community_seeds = {
        "Nova Holding Ltd": hub_a.name,
        "Bluepeak Exports": hub_b.name,
    }
    for p in net.persons:
        if p.tier == "member" and p.name not in (
            "Nalini Das",
            "Kunal Bose",
            "Lata Devi",
            "Omkar Joshi",
        ):
            rep = community_seeds.get(p.org)
            if rep and p.name != rep and rng.random() < 0.4:
                link(p.name, rep)

    for i, f in enumerate(floaters):
        target = hub_a.name if i % 2 == 0 else hub_b.name
        link(f.name, target)

    return net


def build_persons_csv(net: Network) -> bytes:
    lines = ["name,phone,vehicle_no,organization,account_no,city"]
    for p in net.persons:
        lines.append(f"{p.name},{p.phone},{p.vehicle or ''},{p.org},{p.account or ''},{p.city}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_transfers_json(net: Network) -> bytes:
    rng = _rng()
    accounts = [p.account for p in net.persons if p.account]
    if not accounts:
        accounts = ["AC-990001", "AC-990002"]
    records: list[dict[str, object]] = []
    for _ in range(len(accounts) * 2):
        src = rng.choice(accounts)
        dst = rng.choice([a for a in accounts if a != src])
        records.append(
            {
                "from_account": src,
                "to_account": dst,
                "amount": rng.randint(5000, 900000),
                "date": f"2026-0{rng.randint(1, 8)}-{rng.randint(1, 28):02d}",
            }
        )
    return json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")


def build_associations_txt(net: Network) -> bytes:
    rng = _rng()
    sentences: list[str] = []
    verbs = (
        "was seen meeting with",
        "was recorded visiting",
        "held a meeting with",
        "was in contact with",
        "was observed with",
        "was travelling with",
        "was noted dining with",
        "was co-located with",
    )
    for a, bs in net.links.items():
        for b in sorted(bs):
            if rng.random() < 0.5:
                sentences.append(
                    f"{a} {rng.choice(verbs)} {b} on {rng.randint(1, 20):02d}/0{rng.randint(1, 8)} "
                    f"near {rng.choice(CITIES)}."
                )
    for p in net.persons[:100]:
        loc = rng.choice(CITIES)
        sentences.append(
            f"Call detail records show device {p.phone} was registered at "
            f"{loc} cell towers on {rng.randint(1, 20):02d}/0{rng.randint(1, 8)}."
        )
    return ("\n".join(sentences) + "\n").encode("utf-8")


def expected_entity_tally(net: Network) -> dict[str, int]:
    phones = {p.phone for p in net.persons}
    vehicles = {p.vehicle for p in net.persons if p.vehicle}
    accounts = {p.account for p in net.persons if p.account}
    orgs = {p.org for p in net.persons}
    locations = set(CITIES)
    return {
        "person": len(net.persons),
        "phone": len(phones),
        "vehicle": len(vehicles),
        "account": len(accounts),
        "organization": len(orgs),
        "location": len(locations),
        "total": len(net.persons)
        + len(phones)
        + len(vehicles)
        + len(accounts)
        + len(orgs)
        + len(locations),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sih_demo_seed")
    out_dir.mkdir(parents=True, exist_ok=True)
    net = build_network()
    (out_dir / "persons.csv").write_bytes(build_persons_csv(net))
    (out_dir / "transfers.json").write_bytes(build_transfers_json(net))
    (out_dir / "associations.txt").write_bytes(build_associations_txt(net))
    print("wrote evidence files to", out_dir)
    print("expected entity tally:", expected_entity_tally(net))
    print("association links:", sum(len(s) for s in net.links.values()) // 2)
