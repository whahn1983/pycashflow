"""Tests for the email balance timestamp capture in getemail.process_email_balances.

Covers the helper that derives a UTC timestamp from a message's Date header
plus the end-to-end ingestion path that persists ``balance_email_datetime``
on the Email config row. IMAP is mocked — no network is touched.
"""

from __future__ import annotations

import email as email_pkg
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from werkzeug.security import generate_password_hash

from conftest import (  # noqa: E402
    _db as db,
    _Balance as Balance,
    _User as User,
    _Email as Email,
    _getemail as getemail,
)
from app.crypto_utils import encrypt_password


# ── _email_message_datetime_utc ─────────────────────────────────────────────


class TestEmailMessageDatetimeHelper:
    def _build_msg(self, date_header: str | None):
        raw_parts = []
        if date_header is not None:
            raw_parts.append(f"Date: {date_header}")
        raw_parts.extend(
            [
                "From: alerts@bank.com",
                "Subject: balance",
                "Content-Type: text/plain",
                "",
                "Balance: $1234.56",
            ]
        )
        raw = ("\r\n".join(raw_parts)).encode()
        return email_pkg.message_from_bytes(raw)

    def test_parses_rfc5322_date_header_into_naive_utc(self):
        msg = self._build_msg("Sun, 24 May 2026 14:00:00 +0200")
        result = getemail._email_message_datetime_utc(msg)
        assert result == datetime(2026, 5, 24, 12, 0, 0)
        assert result.tzinfo is None

    def test_naive_date_header_assumed_utc(self):
        msg = self._build_msg("Sun, 24 May 2026 14:00:00 -0000")
        result = getemail._email_message_datetime_utc(msg)
        assert result == datetime(2026, 5, 24, 14, 0, 0)

    def test_missing_date_header_falls_back_to_now_utc(self):
        msg = self._build_msg(None)
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        result = getemail._email_message_datetime_utc(msg)
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before - timedelta(seconds=2) <= result <= after + timedelta(seconds=2)
        assert result.tzinfo is None

    def test_unparseable_date_header_falls_back_to_now_utc(self):
        msg = self._build_msg("not a real date")
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        result = getemail._email_message_datetime_utc(msg)
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before - timedelta(seconds=2) <= result <= after + timedelta(seconds=2)


# ── End-to-end: balance_email_datetime persisted on Email config ────────────


def _build_balance_email_bytes(
    subject: str = "balance alert",
    sender: str = "alerts@bank.com",
    date_header: str = "Sun, 24 May 2026 09:30:00 +0000",
    body: str = "Your balance is $1234.56 USD today.",
    auth_results: str | None = "mx.test.local; dkim=pass; spf=pass; dmarc=pass",
) -> bytes:
    lines = [
        f"From: {sender}",
        f"Subject: {subject}",
        f"Date: {date_header}",
    ]
    if auth_results is not None:
        lines.append(f"Authentication-Results: {auth_results}")
    lines.extend(
        [
            "Content-Type: text/plain",
            "",
            body,
        ]
    )
    return ("\r\n".join(lines)).encode()


class TestProcessEmailBalancesPersistsDatetime:
    @pytest.fixture()
    def email_user(self, flask_app):
        """Create a fresh user with an Email config; clean up after the test."""
        with flask_app.app_context():
            user = User(
                email=f"getemail-{datetime.utcnow().timestamp()}@test.local",
                password=generate_password_hash("pw", method="scrypt"),
                name="Email User",
                admin=True,
                is_active=True,
            )
            db.session.add(user)
            db.session.commit()
            cfg = Email(
                user_id=user.id,
                email="ingest@example.com",
                password=encrypt_password("imap-pw"),
                server="imap.example.com",
                subjectstr="balance alert",
                startstr="$",
                endstr=" USD",
                allowed_sender="alerts@bank.com",
            )
            db.session.add(cfg)
            db.session.commit()
            user_id = user.id

        yield user_id

        with flask_app.app_context():
            Email.query.filter_by(user_id=user_id).delete()
            Balance.query.filter_by(user_id=user_id).delete()
            User.query.filter_by(id=user_id).delete()
            db.session.commit()

    def _mock_imap(self, raw_emails: list[bytes]) -> MagicMock:
        imap = MagicMock()
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = (
            "OK",
            [b" ".join(str(i + 1).encode() for i in range(len(raw_emails)))],
        )

        def _fetch(eid, _spec):
            idx = int(eid) - 1
            return (
                "OK",
                [(b"1 (RFC822 {1})", raw_emails[idx])],
            )

        imap.fetch.side_effect = _fetch
        return imap

    def test_stores_balance_email_datetime_from_date_header(
        self, flask_app, email_user
    ):
        raw = _build_balance_email_bytes(
            date_header="Sun, 24 May 2026 09:30:00 +0000"
        )
        with flask_app.app_context():
            with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
                mock_ssl.return_value = self._mock_imap([raw])
                getemail.process_email_balances()

            cfg = Email.query.filter_by(user_id=email_user).first()
            assert cfg.balance_email_datetime == datetime(2026, 5, 24, 9, 30, 0)
            assert cfg.balance_email_datetime.tzinfo is None

    def test_records_datetime_even_when_balance_is_duplicate(
        self, flask_app, email_user
    ):
        # Pre-seed today's balance to match the email value so the parser
        # treats it as a duplicate. The email timestamp must still be saved.
        with flask_app.app_context():
            db.session.add(
                Balance(user_id=email_user, amount=1234.56, date=datetime.today().date())
            )
            db.session.commit()

            raw = _build_balance_email_bytes(
                date_header="Sun, 24 May 2026 09:30:00 +0000"
            )
            with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
                mock_ssl.return_value = self._mock_imap([raw])
                getemail.process_email_balances()

            cfg = Email.query.filter_by(user_id=email_user).first()
            assert cfg.balance_email_datetime == datetime(2026, 5, 24, 9, 30, 0)

    def test_newest_email_timestamp_wins_when_multiple_messages(
        self, flask_app, email_user
    ):
        older = _build_balance_email_bytes(
            date_header="Sun, 24 May 2026 08:00:00 +0000",
            body="Your balance is $100.00 USD today.",
        )
        newer = _build_balance_email_bytes(
            date_header="Sun, 24 May 2026 10:00:00 +0000",
            body="Your balance is $200.00 USD today.",
        )
        with flask_app.app_context():
            with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
                mock_ssl.return_value = self._mock_imap([older, newer])
                getemail.process_email_balances()

            cfg = Email.query.filter_by(user_id=email_user).first()
            # Newer Date header is the persisted timestamp.
            assert cfg.balance_email_datetime == datetime(2026, 5, 24, 10, 0, 0)
            # The newest email's body is what set the balance.
            row = Balance.query.filter_by(
                user_id=email_user, date=datetime.today().date()
            ).first()
            assert float(row.amount) == pytest.approx(200.00)

    def test_email_ingestion_does_not_stamp_manual_balance_timestamp(
        self, flask_app, email_user
    ):
        """Email-derived balances must not set the user's manual entry
        timestamp — that field is reserved for genuine manual entries."""
        raw = _build_balance_email_bytes(
            date_header="Sun, 24 May 2026 09:30:00 +0000"
        )
        with flask_app.app_context():
            assert User.query.get(email_user).last_manual_balance_entry_at is None
            with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
                mock_ssl.return_value = self._mock_imap([raw])
                getemail.process_email_balances()

            assert User.query.get(email_user).last_manual_balance_entry_at is None

    def test_falls_back_to_processing_time_when_date_header_missing(
        self, flask_app, email_user
    ):
        lines = [
            "From: alerts@bank.com",
            "Subject: balance alert",
            "Authentication-Results: mx.test.local; dkim=pass; spf=pass; dmarc=pass",
            "Content-Type: text/plain",
            "",
            "Your balance is $42.00 USD today.",
        ]
        raw = ("\r\n".join(lines)).encode()
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        with flask_app.app_context():
            with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
                mock_ssl.return_value = self._mock_imap([raw])
                getemail.process_email_balances()

            cfg = Email.query.filter_by(user_id=email_user).first()
            after = datetime.now(timezone.utc).replace(tzinfo=None)
            assert cfg.balance_email_datetime is not None
            assert (
                before - timedelta(seconds=5)
                <= cfg.balance_email_datetime
                <= after + timedelta(seconds=5)
            )


# ── Authentication enforcement (H1) ─────────────────────────────────────────


class TestAuthResultHelpers:
    def test_parse_first_header_result_wins_per_mechanism(self):
        # The outermost (first) header is the provider-stamped one and is
        # trusted; results from later headers must not override it.
        raw = (
            "From: alerts@bank.com\r\n"
            "Subject: balance\r\n"
            "Authentication-Results: mx.test.local; dkim=pass; spf=pass; dmarc=pass\r\n"
            "Authentication-Results: deeper.example; dkim=fail; spf=fail; dmarc=fail\r\n"
            "Content-Type: text/plain\r\n\r\nx"
        ).encode()
        msg = email_pkg.message_from_bytes(raw)

        assert getemail._parse_auth_results(msg) == {
            "dkim": "pass",
            "spf": "pass",
            "dmarc": "pass",
        }

    def test_authentication_passes_policy(self):
        assert getemail._authentication_passes({"dmarc": "pass"})[0] is True
        assert getemail._authentication_passes(
            {"spf": "pass", "dkim": "pass"}
        )[0] is True
        # Missing results, partial passes, and explicit failures all fail.
        assert getemail._authentication_passes({})[0] is False
        assert getemail._authentication_passes({"spf": "pass"})[0] is False
        assert getemail._authentication_passes(
            {"dmarc": "fail", "spf": "pass", "dkim": "pass"}
        )[0] is True  # SPF+DKIM still authenticate even if DMARC reports fail
        assert getemail._authentication_passes(
            {"dmarc": "fail", "spf": "fail", "dkim": "fail"}
        )[0] is False


class TestProcessEmailBalancesEnforcesAuth:
    """End-to-end: the ingestion path rejects spoofable mail (H1 fix)."""

    @pytest.fixture()
    def email_user(self, flask_app):
        with flask_app.app_context():
            user = User(
                email=f"authcheck-{datetime.utcnow().timestamp()}@test.local",
                password=generate_password_hash("pw", method="scrypt"),
                name="Auth User",
                admin=True,
                is_active=True,
            )
            db.session.add(user)
            db.session.commit()
            cfg = Email(
                user_id=user.id,
                email="ingest@example.com",
                password=encrypt_password("imap-pw"),
                server="imap.example.com",
                subjectstr="balance alert",
                startstr="$",
                endstr=" USD",
                allowed_sender="alerts@bank.com",
            )
            db.session.add(cfg)
            db.session.commit()
            user_id = user.id
        yield user_id
        with flask_app.app_context():
            Email.query.filter_by(user_id=user_id).delete()
            Balance.query.filter_by(user_id=user_id).delete()
            User.query.filter_by(id=user_id).delete()
            db.session.commit()

    def _run(self, flask_app, raw_emails):
        with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
            imap = MagicMock()
            imap.select.return_value = ("OK", [b"1"])
            imap.search.return_value = (
                "OK",
                [b" ".join(str(i + 1).encode() for i in range(len(raw_emails)))],
            )

            def _fetch(eid, _spec):
                return ("OK", [(b"1 (RFC822 {1})", raw_emails[int(eid) - 1])])

            imap.fetch.side_effect = _fetch
            mock_ssl.return_value = imap
            getemail.process_email_balances()

    def _today_balance(self, user_id):
        return Balance.query.filter_by(
            user_id=user_id, date=datetime.today().date()
        ).first()

    def test_rejects_email_with_no_auth_results(self, flask_app, email_user):
        raw = _build_balance_email_bytes(auth_results=None)
        with flask_app.app_context():
            self._run(flask_app, [raw])
            assert self._today_balance(email_user) is None

    def test_rejects_email_failing_dmarc(self, flask_app, email_user):
        raw = _build_balance_email_bytes(
            auth_results="mx.test.local; dkim=fail; spf=fail; dmarc=fail"
        )
        with flask_app.app_context():
            self._run(flask_app, [raw])
            assert self._today_balance(email_user) is None

    def test_accepts_email_passing_auth(self, flask_app, email_user):
        raw = _build_balance_email_bytes()
        with flask_app.app_context():
            self._run(flask_app, [raw])
            row = self._today_balance(email_user)
            assert row is not None
            assert float(row.amount) == pytest.approx(1234.56)

    def test_rejects_when_sender_not_allowed(self, flask_app, email_user):
        raw = _build_balance_email_bytes(sender="evil@phisher.com")
        with flask_app.app_context():
            self._run(flask_app, [raw])
            assert self._today_balance(email_user) is None

    def test_skips_user_without_allowed_sender(self, flask_app, email_user):
        with flask_app.app_context():
            cfg = Email.query.filter_by(user_id=email_user).first()
            cfg.allowed_sender = None
            db.session.commit()
            # Even a fully authenticated message is ignored: ingestion is
            # disabled until an Allowed Sender is configured.
            raw = _build_balance_email_bytes()
            self._run(flask_app, [raw])
            assert self._today_balance(email_user) is None

    def test_auth_disabled_allows_unauthenticated(self, flask_app, email_user):
        raw = _build_balance_email_bytes(auth_results=None)
        with flask_app.app_context():
            flask_app.config["EMAIL_REQUIRE_AUTH_RESULTS"] = False
            try:
                self._run(flask_app, [raw])
                row = self._today_balance(email_user)
                assert row is not None
                assert float(row.amount) == pytest.approx(1234.56)
            finally:
                flask_app.config["EMAIL_REQUIRE_AUTH_RESULTS"] = True


# ── In-app DKIM verification fallback ────────────────────────────────────────


def _build_dkim_signed_email_bytes(
    subject: str = "balance alert",
    sender: str = "alerts@bank.com",
    body: str = "Your balance is $1234.56 USD today.",
    signing_domain: str = "bank.com",
) -> bytes:
    """A message with a DKIM-Signature header but NO Authentication-Results,
    mimicking a custom-domain/self-hosted mailbox that doesn't stamp auth
    headers. The signature is not cryptographically valid here — tests patch
    _verify_dkim_signatures to control the verified-domain outcome."""
    lines = [
        f"From: {sender}",
        f"Subject: {subject}",
        "Date: Sun, 24 May 2026 09:30:00 +0000",
        (
            f"DKIM-Signature: v=1; a=rsa-sha256; d={signing_domain}; s=sel; "
            "h=from:subject:date; bh=abc; b=def"
        ),
        "Content-Type: text/plain",
        "",
        body,
    ]
    return ("\r\n".join(lines)).encode()


class TestDkimDomainAligns:
    def test_exact_domain_match(self):
        assert getemail._dkim_domain_aligns({"bank.com"}, "alerts@bank.com")

    def test_signing_org_domain_aligns_with_subdomain_sender(self):
        # From on a subdomain, signed by the organisational domain.
        assert getemail._dkim_domain_aligns(
            {"bankofamerica.com"}, "alerts@ealerts.bankofamerica.com"
        )

    def test_signing_subdomain_aligns_with_org_sender(self):
        assert getemail._dkim_domain_aligns(
            {"ealerts.bank.com"}, "alerts@bank.com"
        )

    def test_unrelated_domain_does_not_align(self):
        assert not getemail._dkim_domain_aligns({"phisher.com"}, "alerts@bank.com")

    def test_empty_inputs_do_not_align(self):
        assert not getemail._dkim_domain_aligns(set(), "alerts@bank.com")
        assert not getemail._dkim_domain_aligns({"bank.com"}, "")


class TestVerifyDkimSignatures:
    def test_returns_verified_signing_domain(self):
        fake_dkim = MagicMock()
        verifier = MagicMock()
        verifier.verify.return_value = True
        verifier.domain = b"bank.com"
        fake_dkim.DKIM.return_value = verifier
        with patch.dict("sys.modules", {"dkim": fake_dkim}):
            result = getemail._verify_dkim_signatures(b"raw", 1)
        assert result == {"bank.com"}

    def test_failed_verification_excluded(self):
        fake_dkim = MagicMock()
        verifier = MagicMock()
        verifier.verify.return_value = False
        fake_dkim.DKIM.return_value = verifier
        with patch.dict("sys.modules", {"dkim": fake_dkim}):
            result = getemail._verify_dkim_signatures(b"raw", 1)
        assert result == set()

    def test_exception_is_swallowed(self):
        fake_dkim = MagicMock()
        fake_dkim.DKIM.side_effect = RuntimeError("boom")
        with patch.dict("sys.modules", {"dkim": fake_dkim}):
            result = getemail._verify_dkim_signatures(b"raw", 1)
        assert result == set()


class TestProcessEmailBalancesDkimFallback:
    """When the mailbox stamps no Authentication-Results header, ingestion
    falls back to in-app DKIM verification (the custom-domain case)."""

    @pytest.fixture()
    def email_user(self, flask_app):
        with flask_app.app_context():
            user = User(
                email=f"dkim-{datetime.utcnow().timestamp()}@test.local",
                password=generate_password_hash("pw", method="scrypt"),
                name="DKIM User",
                admin=True,
                is_active=True,
            )
            db.session.add(user)
            db.session.commit()
            cfg = Email(
                user_id=user.id,
                email="ingest@example.com",
                password=encrypt_password("imap-pw"),
                server="imap.example.com",
                subjectstr="balance alert",
                startstr="$",
                endstr=" USD",
                allowed_sender="alerts@bank.com",
            )
            db.session.add(cfg)
            db.session.commit()
            user_id = user.id
        yield user_id
        with flask_app.app_context():
            Email.query.filter_by(user_id=user_id).delete()
            Balance.query.filter_by(user_id=user_id).delete()
            User.query.filter_by(id=user_id).delete()
            db.session.commit()

    def _run(self, flask_app, raw_emails):
        with patch("app.getemail.imaplib.IMAP4_SSL") as mock_ssl:
            imap = MagicMock()
            imap.select.return_value = ("OK", [b"1"])
            imap.search.return_value = (
                "OK",
                [b" ".join(str(i + 1).encode() for i in range(len(raw_emails)))],
            )

            def _fetch(eid, _spec):
                return ("OK", [(b"1 (RFC822 {1})", raw_emails[int(eid) - 1])])

            imap.fetch.side_effect = _fetch
            mock_ssl.return_value = imap
            getemail.process_email_balances()

    def _today_balance(self, user_id):
        return Balance.query.filter_by(
            user_id=user_id, date=datetime.today().date()
        ).first()

    def test_accepts_when_dkim_verifies_and_aligns(self, flask_app, email_user):
        raw = _build_dkim_signed_email_bytes(signing_domain="bank.com")
        with flask_app.app_context():
            with patch(
                "app.getemail._verify_dkim_signatures",
                return_value={"bank.com"},
            ) as mock_verify:
                self._run(flask_app, [raw])
            mock_verify.assert_called_once()
            row = self._today_balance(email_user)
            assert row is not None
            assert float(row.amount) == pytest.approx(1234.56)

    def test_rejects_when_dkim_domain_does_not_align(self, flask_app, email_user):
        raw = _build_dkim_signed_email_bytes(signing_domain="phisher.com")
        with flask_app.app_context():
            with patch(
                "app.getemail._verify_dkim_signatures",
                return_value={"phisher.com"},
            ):
                self._run(flask_app, [raw])
            assert self._today_balance(email_user) is None

    def test_rejects_when_dkim_does_not_verify(self, flask_app, email_user):
        raw = _build_dkim_signed_email_bytes()
        with flask_app.app_context():
            with patch(
                "app.getemail._verify_dkim_signatures", return_value=set()
            ):
                self._run(flask_app, [raw])
            assert self._today_balance(email_user) is None

    def test_dkim_fallback_disabled_rejects(self, flask_app, email_user):
        raw = _build_dkim_signed_email_bytes(signing_domain="bank.com")
        with flask_app.app_context():
            flask_app.config["EMAIL_VERIFY_DKIM"] = False
            try:
                with patch(
                    "app.getemail._verify_dkim_signatures",
                    return_value={"bank.com"},
                ) as mock_verify:
                    self._run(flask_app, [raw])
                # Fallback disabled: DKIM verification must not even run.
                mock_verify.assert_not_called()
                assert self._today_balance(email_user) is None
            finally:
                flask_app.config["EMAIL_VERIFY_DKIM"] = True

    def test_provider_auth_header_skips_dkim_fallback(self, flask_app, email_user):
        # When the provider DID stamp a passing Authentication-Results header,
        # the DKIM fallback is unnecessary and must not run.
        raw = _build_balance_email_bytes(
            auth_results="mx.test.local; dkim=pass; spf=pass; dmarc=pass"
        )
        with flask_app.app_context():
            with patch("app.getemail._verify_dkim_signatures") as mock_verify:
                self._run(flask_app, [raw])
            mock_verify.assert_not_called()
            assert self._today_balance(email_user) is not None
