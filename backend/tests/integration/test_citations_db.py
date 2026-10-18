"""DB-backed citation validation: existence, scope, locators, quotes, visibility.

Runs against the live PostgreSQL like the other tests in this directory (the
session conftest skips the suite when infrastructure is unreachable). Covers
what unit tests cannot: row existence, case scoping through the evidence file,
field locators against stored ``raw_data``, quote equality against stored
values, and the per-call cross-case visibility recheck.

The admin short-circuit of ``case_visible_to`` needs seeded role rows from
bootstrap and is covered by the API suite's role-based tests; here we exercise
owner, member and stranger paths directly.
"""

from __future__ import annotations

import uuid

from app.db.postgres import Database
from app.models import Case, CaseMember, DerivedArtifact, EvidenceFile, SourceRecord, User
from app.services.citations import CitationRef, case_visible_to, validate_citation
from app.services.structured_extraction import canonical_hash
from sqlalchemy import delete, select

RAW = {"person_name": "Rahul Patil", "amount": 1000.00, "txn_date": "2026-03-15"}


async def _make_user(database: Database, tag: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            User(
                id=user_id,
                username=f"{tag}-{user_id.hex[:10]}",
                email=f"{tag}-{user_id.hex[:10]}@citation.test",
                password_hash="x" * 60,
                status="ACTIVE",
            )
        )
        await session.commit()
    return user_id


async def _make_case(database: Database, tag: str, owner_id: uuid.UUID | None = None) -> uuid.UUID:
    case_id = uuid.uuid4()
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            Case(
                id=case_id,
                case_number=f"cit-{tag}-{uuid.uuid4().hex[:8]}",
                title="citation validation case",
                status="open",
                owner_id=owner_id,
            )
        )
        await session.commit()
    return case_id


async def _make_record(database: Database, case_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    factory = database.session_factory()
    async with factory() as session:
        evidence = EvidenceFile(
            case_id=str(case_id),
            original_filename="statement.csv",
            stored_key=f"cases/{case_id}/statement.csv",
            content_type="text/csv",
            file_size=128,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            format="csv",
            status="parsed",
        )
        session.add(evidence)
        await session.flush()
        record = SourceRecord(
            evidence_file_id=str(evidence.id),
            record_no=1,
            raw_data=RAW,
            status="parsed",
        )
        session.add(record)
        await session.commit()
        return evidence.id, record.id


async def _make_artifact(database: Database, case_id: uuid.UUID) -> uuid.UUID:
    payload = {"amount": "1000.00", "person_name": "Rahul Patil"}
    factory = database.session_factory()
    async with factory() as session:
        artifact = DerivedArtifact(
            case_id=str(case_id),
            kind="extraction",
            origin="llm",
            status="pending_review",
            validation_status="valid",
            payload=payload,
            content_hash=canonical_hash(payload),
            parser_version="deterministic:1",
        )
        session.add(artifact)
        await session.commit()
        return artifact.id


async def _add_member(database: Database, case_id: uuid.UUID, user_id: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        session.add(CaseMember(case_id=case_id, user_id=user_id, role="collaborator"))
        await session.commit()


async def _purge(
    database: Database, *, case_ids: list[uuid.UUID], user_ids: list[uuid.UUID]
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        for case_id in case_ids:
            evidence_ids = list(
                (
                    await session.execute(
                        select(EvidenceFile.id).where(EvidenceFile.case_id == str(case_id))
                    )
                ).scalars()
            )
            if evidence_ids:
                await session.execute(
                    delete(SourceRecord).where(SourceRecord.evidence_file_id.in_(evidence_ids))
                )
            await session.execute(delete(EvidenceFile).where(EvidenceFile.case_id == str(case_id)))
            await session.execute(delete(CaseMember).where(CaseMember.case_id == case_id))
            await session.execute(
                delete(DerivedArtifact).where(DerivedArtifact.case_id == str(case_id))
            )
            await session.execute(delete(Case).where(Case.id == case_id))
        for user_id in user_ids:
            await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


class _Ctx:
    """Per-test bookkeeping of created rows for teardown."""

    def __init__(self) -> None:
        self.cases: list[uuid.UUID] = []
        self.users: list[uuid.UUID] = []


async def test_malformed_and_missing_refs_fail(database: Database) -> None:
    ctx = _Ctx()
    owner = await _make_user(database, "alone")
    case_id = await _make_case(database, "a", owner)
    ctx.cases.append(case_id)
    ctx.users.append(owner)
    user = User(
        id=owner,
        username="loaded",
        email="loaded@citation.test",
        password_hash="x" * 60,
    )
    try:
        factory = database.session_factory()
        async with factory() as session:
            bad_id = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(kind="source_record", id="not-a-uuid"),
            )
            assert not bad_id.ok
            assert "citation_invalid_id" in bad_id.codes

            unknown_kind = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(kind="telepathy", id=str(uuid.uuid4())),
            )
            assert not unknown_kind.ok
            assert "citation_unknown_kind" in unknown_kind.codes

            missing = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(kind="source_record", id=str(uuid.uuid4())),
            )
            assert not missing.ok
            assert missing.codes == ("citation_record_missing",)
    finally:
        await _purge(database, case_ids=ctx.cases, user_ids=ctx.users)


async def test_valid_citation_and_quote_equality(database: Database) -> None:
    ctx = _Ctx()
    owner = await _make_user(database, "own")
    case_id = await _make_case(database, "b", owner)
    ctx.cases.append(case_id)
    ctx.users.append(owner)
    _, record_id = await _make_record(database, case_id)
    user = User(id=owner, username="loaded", email="loaded@citation.test", password_hash="x" * 60)
    try:
        factory = database.session_factory()
        async with factory() as session:
            good = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="source_record",
                    id=str(record_id),
                    locator={"field": "amount"},
                    quote={"field": "amount", "value": 1000.00},
                ),
            )
            assert good.ok, good.codes
            assert good.resolved_case_id == str(case_id)
            assert good.actual == {"amount": 1000.00}

            grouped = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="source_record",
                    id=str(record_id),
                    quote={"field": "amount", "value": "1,000.00"},
                ),
            )
            assert grouped.ok, grouped.codes
    finally:
        await _purge(database, case_ids=ctx.cases, user_ids=ctx.users)


async def test_scope_mismatch_and_claimed_case_mismatch(database: Database) -> None:
    ctx = _Ctx()
    stranger = await _make_user(database, "str")
    case_a = await _make_case(database, "a")
    case_b = await _make_case(database, "b")
    ctx.cases.extend([case_a, case_b])
    ctx.users.append(stranger)
    _, record_id = await _make_record(database, case_a)
    user = User(
        id=stranger, username="loaded", email="loaded@citation.test", password_hash="x" * 60
    )
    try:
        factory = database.session_factory()
        async with factory() as session:
            # Record lives in case A but the claim cites case B: wrong case.
            wrong = await validate_citation(
                session,
                user=user,
                case_id=case_b,
                ref=CitationRef(kind="source_record", id=str(record_id)),
            )
            assert not wrong.ok
            assert wrong.codes == ("citation_wrong_case",)
            assert wrong.resolved_case_id == str(case_a)

            # Claim asserts a case id that differs from the record's real scope.
            claimed = await validate_citation(
                session,
                user=user,
                case_id=case_a,
                ref=CitationRef(kind="source_record", id=str(record_id), case_id=str(case_b)),
            )
            assert not claimed.ok
            assert "citation_case_mismatch" in claimed.codes
    finally:
        await _purge(database, case_ids=ctx.cases, user_ids=ctx.users)


async def test_locator_and_quote_failures(database: Database) -> None:
    ctx = _Ctx()
    owner = await _make_user(database, "loc")
    case_id = await _make_case(database, "c", owner)
    ctx.cases.append(case_id)
    ctx.users.append(owner)
    _, record_id = await _make_record(database, case_id)
    user = User(id=owner, username="loaded", email="loaded@citation.test", password_hash="x" * 60)
    try:
        factory = database.session_factory()
        async with factory() as session:
            bad_locator = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="source_record",
                    id=str(record_id),
                    locator={"field": "transfer_amount"},
                ),
            )
            assert not bad_locator.ok
            assert bad_locator.codes == ("citation_locator_invalid",)

            bad_quote = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="source_record",
                    id=str(record_id),
                    quote={"field": "amount", "value": 999.99},
                ),
            )
            assert not bad_quote.ok
            assert bad_quote.codes == ("citation_value_mismatch",)
            assert bad_quote.actual == {"amount": 1000.00}

            quote_unknown_field = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="source_record",
                    id=str(record_id),
                    quote={"field": "beneficiary", "value": "Rahul Patil"},
                ),
            )
            assert not quote_unknown_field.ok
            assert "citation_locator_invalid" in quote_unknown_field.codes
    finally:
        await _purge(database, case_ids=ctx.cases, user_ids=ctx.users)


async def test_derived_artifact_citations(database: Database) -> None:
    ctx = _Ctx()
    owner = await _make_user(database, "art")
    case_id = await _make_case(database, "d", owner)
    ctx.cases.append(case_id)
    ctx.users.append(owner)
    artifact_id = await _make_artifact(database, case_id)
    user = User(id=owner, username="loaded", email="loaded@citation.test", password_hash="x" * 60)
    try:
        factory = database.session_factory()
        async with factory() as session:
            good = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="derived_artifact",
                    id=str(artifact_id),
                    quote={"field": "amount", "value": "1000.00"},
                ),
            )
            assert good.ok, good.codes

            bad = await validate_citation(
                session,
                user=user,
                case_id=case_id,
                ref=CitationRef(
                    kind="derived_artifact",
                    id=str(artifact_id),
                    quote={"field": "narrative", "value": "rent"},
                ),
            )
            assert not bad.ok
            assert bad.codes == ("citation_locator_invalid",)
    finally:
        await _purge(database, case_ids=ctx.cases, user_ids=ctx.users)


async def test_cross_case_visibility_is_rechecked_per_call(database: Database) -> None:
    ctx = _Ctx()
    owner = await _make_user(database, "vis-owner")
    member = await _make_user(database, "vis-member")
    stranger = await _make_user(database, "vis-stranger")
    case_id = await _make_case(database, "e", owner)
    ctx.cases.append(case_id)
    ctx.users.extend([owner, member, stranger])
    await _add_member(database, case_id, member)
    other_case = await _make_case(database, "f", owner)
    ctx.cases.append(other_case)
    _, record_id = await _make_record(database, case_id)

    def _user(uid: uuid.UUID) -> User:
        return User(id=uid, username="loaded", email="loaded@citation.test", password_hash="x" * 60)

    try:
        factory = database.session_factory()
        async with factory() as session:
            # Owner and member see the case; stranger does not.
            assert await case_visible_to(session, _user(owner), case_id) is True
            assert await case_visible_to(session, _user(member), case_id) is True
            assert await case_visible_to(session, _user(stranger), case_id) is False

            # Opt-in cross-case succeeds for a visible principal...
            owner_ok = await validate_citation(
                session,
                user=_user(owner),
                case_id=other_case,
                ref=CitationRef(kind="source_record", id=str(record_id)),
                allow_cross_case=True,
            )
            assert owner_ok.ok, owner_ok.codes
            assert owner_ok.resolved_case_id == str(case_id)

            member_ok = await validate_citation(
                session,
                user=_user(member),
                case_id=other_case,
                ref=CitationRef(kind="source_record", id=str(record_id)),
                allow_cross_case=True,
            )
            assert member_ok.ok, member_ok.codes

            # ...but never for a principal without visibility.
            denied = await validate_citation(
                session,
                user=_user(stranger),
                case_id=other_case,
                ref=CitationRef(kind="source_record", id=str(record_id)),
                allow_cross_case=True,
            )
            assert not denied.ok
            assert denied.codes == ("citation_unauthorized",)

            # Without the explicit opt-in even the owner gets wrong-case.
            no_opt_in = await validate_citation(
                session,
                user=_user(owner),
                case_id=other_case,
                ref=CitationRef(kind="source_record", id=str(record_id)),
                allow_cross_case=False,
            )
            assert not no_opt_in.ok
            assert no_opt_in.codes == ("citation_wrong_case",)
    finally:
        await _purge(database, case_ids=ctx.cases, user_ids=ctx.users)
