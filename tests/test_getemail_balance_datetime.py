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
) -> bytes:
    lines = [
        f"From: {sender}",
        f"Subject: {subject}",
        f"Date: {date_header}",
        "Content-Type: text/plain",
        "",
        body,
    ]
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
                allowed_sender=None,
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
