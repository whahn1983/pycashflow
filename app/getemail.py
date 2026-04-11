#!/usr/bin/env python3
"""
Email balance import script for pycashflow.
Processes IMAP email inboxes to extract and import balance information.

This script can be run standalone from cron or called from within the application.
"""
import os
import sys
import logging

# When run as standalone script, add parent directory to path for imports
# This allows 'from app import ...' to work when called from cron
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import re
import imaplib
import email
import smtplib
from flask import current_app
from email.header import decode_header
from email.utils import parseaddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from app import db
from app.models import User, Email, Balance, GlobalEmailSettings
from app.crypto_utils import decrypt_password

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sender / authentication-header helpers
# ---------------------------------------------------------------------------

def _extract_sender_address(from_header: str) -> str:
    """Return the bare, lower-cased email address from a From header value.

    Handles both plain addresses ('alerts@bank.com') and RFC 5322 display-name
    form ('"Bank Alerts" <alerts@bank.com>').  Returns an empty string when
    the header cannot be parsed.
    """
    _, addr = parseaddr(from_header or "")
    return addr.lower().strip()


def _sender_is_allowed(sender_address: str, allowed_sender: str) -> bool:
    """Return True when *sender_address* satisfies the *allowed_sender* pattern.

    Pattern formats (case-insensitive):
      '@domain.com'      – any address whose domain part equals domain.com
      'user@domain.com'  – exact address match
    """
    allowed = (allowed_sender or "").strip().lower()
    sender = (sender_address or "").strip().lower()
    if not allowed:
        return True  # no restriction configured; caller must warn
    if allowed.startswith("@"):
        return sender.endswith(allowed)
    return sender == allowed


def _parse_auth_results(msg) -> dict:
    """Parse *Authentication-Results* headers and return a mapping of
    mechanism → result for dkim, spf, and dmarc.

    Only the first result found for each mechanism is kept (the outermost
    Authentication-Results header, added by the user's own mail provider,
    appears first in the message).

    Example return value: {'dkim': 'pass', 'spf': 'pass', 'dmarc': 'pass'}
    """
    results: dict = {}
    for header_value in msg.get_all("Authentication-Results") or []:
        for mech, result in re.findall(
            r"\b(dkim|spf|dmarc)=(pass|fail|softfail|none|neutral|permerror|temperror)\b",
            header_value,
            re.IGNORECASE,
        ):
            key = mech.lower()
            if key not in results:
                results[key] = result.lower()
    return results


def process_email_balances():
    """
    Process email inboxes for all users with email settings configured
    and update their balance information from bank emails.

    This function supports both SQLite and PostgreSQL through SQLAlchemy.
    """
    # OUTER LOOP: Get all users with email settings configured
    users_with_email = db.session.query(User, Email).join(
        Email, User.id == Email.user_id
    ).all()

    logger.info("Email import run discovered %d user email configuration(s)", len(users_with_email))

    for user, email_config in users_with_email:
        user_id = user.id
        username = email_config.email
        password = decrypt_password(email_config.password)
        imap_server = email_config.server
        subjectstr = email_config.subjectstr
        startstr = email_config.startstr
        endstr = email_config.endstr

        try:
            # Create IMAP connection for THIS user
            imap = imaplib.IMAP4_SSL(imap_server)
            imap.login(username, password)

            status, messages = imap.select("INBOX", readonly=True)

            # Filter for emails from the past day to limit inbox processing
            # IMAP SINCE searches for messages with Date on or after the specified date
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
            status, message_ids = imap.search(None, f'SINCE {yesterday}')

            # Parse message IDs from the search result
            if message_ids[0]:
                email_ids = message_ids[0].split()
            else:
                email_ids = []

            emails_scanned = len(email_ids)
            emails_allowed = 0
            emails_rejected = 0
            logger.info("Found %d email(s) from the past day for user %s", emails_scanned, user_id)

            email_content = {}

            # INNER LOOP: Process only emails from the past day
            for email_id in email_ids:
                try:
                    res, msg = imap.fetch(email_id, "(RFC822)")
                    for response in msg:
                        if isinstance(response, tuple):
                            msg = email.message_from_bytes(response[1])

                            # Decode subject
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes):
                                try:
                                    subject = subject.decode(encoding)
                                except (UnicodeDecodeError, LookupError) as exc:
                                    logger.debug(
                                        "Could not decode subject for user %s: %s",
                                        user_id, exc,
                                    )
                                    subject = "subject"

                            # Decode sender
                            From, encoding = decode_header(msg.get("From"))[0]
                            if isinstance(From, bytes):
                                try:
                                    From = From.decode(encoding)
                                except (UnicodeDecodeError, LookupError) as exc:
                                    logger.debug(
                                        "Could not decode From header for user %s: %s",
                                        user_id, exc,
                                    )

                            # --- Sender validation ---
                            sender_address = _extract_sender_address(
                                From if isinstance(From, str) else str(From or "")
                            )
                            allowed_sender = email_config.allowed_sender
                            if not allowed_sender:
                                logger.debug(
                                    "No allowed_sender configured for user %s; "
                                    "processing email without sender check",
                                    user_id,
                                )
                                emails_allowed += 1
                            elif not _sender_is_allowed(sender_address, allowed_sender):
                                emails_rejected += 1
                                logger.debug(
                                    "Rejected email for user %s: "
                                    "sender does not match allowed_sender",
                                    user_id,
                                )
                                break  # skip remaining responses for this email_id
                            else:
                                emails_allowed += 1

                            # --- Authentication-Results inspection ---
                            auth = _parse_auth_results(msg)
                            for mech in ("dkim", "spf", "dmarc"):
                                result = auth.get(mech)
                                if result is None:
                                    logger.debug(
                                        "No %s result in Authentication-Results for user %s",
                                        mech.upper(), user_id,
                                    )
                                elif result != "pass":
                                    logger.debug(
                                        "user %s: %s check did not pass",
                                        user_id, mech.upper(),
                                    )
                                else:
                                    logger.debug(
                                        "user %s: %s=pass",
                                        user_id, mech.upper(),
                                    )

                            # Extract email body
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))
                                    body = None
                                    try:
                                        body = part.get_payload(decode=True).decode()
                                    except (UnicodeDecodeError, AttributeError) as exc:
                                        logger.debug(
                                            "Could not decode part body for user %s: %s",
                                            user_id, exc,
                                        )
                                    if (
                                        content_type == "text/plain"
                                        and "attachment" not in content_disposition
                                        and body is not None
                                    ):
                                        email_content[subject] = body
                            else:
                                content_type = msg.get_content_type()
                                body = msg.get_payload(decode=True).decode()
                                if content_type == "text/plain":
                                    email_content[subject] = body
                except Exception as exc:
                    logger.debug(
                        "Skipping an email for user %s due to error: %s",
                        user_id, exc,
                    )

            logger.info(
                "User %s: scanned %d email(s), %d passed sender check, %d rejected",
                user_id, emails_scanned, emails_allowed, emails_rejected,
            )

            # Extract balance from emails for THIS user
            balance_updated = False
            try:
                start_index = email_content[subjectstr].find(startstr) + len(startstr)
                end_index = email_content[subjectstr].find(endstr)
                new_balance = email_content[subjectstr][start_index:end_index].replace(',', '')
                new_balance = new_balance.replace('$', '')
                new_balance = float(new_balance)

                # Insert balance WITH user_id using SQLAlchemy ORM
                balance = Balance(
                    amount=new_balance,
                    date=datetime.today().date(),
                    user_id=user_id
                )
                db.session.add(balance)
                db.session.commit()
                balance_updated = True
                logger.info("Balance updated successfully for user %s", user_id)
            except KeyError:
                # No email with the specified subject found
                pass
            except ValueError as exc:
                logger.warning("Could not parse balance value for user %s: %s", user_id, exc)
            except Exception as exc:
                logger.error("Failed to save balance for user %s: %s", user_id, exc)

            if not balance_updated:
                logger.info("Balance was not updated for user %s (no matching email found)", user_id)

            # Close IMAP connection for THIS user
            imap.close()
            imap.logout()

        except Exception as exc:
            # Failed to connect to IMAP for this user - skip to next user
            logger.exception("Failed to process emails for user %s", user_id)
            continue


def send_new_user_notification(new_user_name, new_user_email):
    """
    Send an email notification to the global admin when a new user registers.

    Args:
        new_user_name: Name of the newly registered user
        new_user_email: Email of the newly registered user

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Get the global admin user
        global_admin = User.query.filter_by(is_global_admin=True).first()

        if not global_admin:
            logger.warning("No global admin found, skipping new user notification")
            return False

        # Get global email settings
        email_settings = GlobalEmailSettings.query.first()

        if not email_settings:
            logger.warning("No global email settings configured, skipping new user notification")
            return False

        # Extract email credentials from global settings
        from_email = email_settings.email
        password = decrypt_password(email_settings.password)
        smtp_server = email_settings.smtp_server

        # Create the email message
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = global_admin.email  # Send to the global admin's email
        msg['Subject'] = 'New User Registration - PyCashFlow'

        # Create plain text version
        text_content = f"""
A new user has registered on PyCashFlow.

Name: {new_user_name}
Email: {new_user_email}
Registration Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This user account is currently inactive and requires approval before they can log in.
Please log in to your PyCashFlow account to activate this user.
"""

        # Create HTML version
        html_content = f"""
<html>
  <body>
    <h2>New User Registration</h2>
    <p>A new user has registered on PyCashFlow.</p>
    <table style="border-collapse: collapse; margin-top: 10px;">
      <tr>
        <td style="padding: 5px; font-weight: bold;">Name:</td>
        <td style="padding: 5px;">{new_user_name}</td>
      </tr>
      <tr>
        <td style="padding: 5px; font-weight: bold;">Email:</td>
        <td style="padding: 5px;">{new_user_email}</td>
      </tr>
      <tr>
        <td style="padding: 5px; font-weight: bold;">Registration Date:</td>
        <td style="padding: 5px;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td>
      </tr>
    </table>
    <p style="margin-top: 15px;">
      <strong>Note:</strong> This user account is currently inactive and requires approval before they can log in.
      Please log in to your PyCashFlow account to activate this user.
    </p>
  </body>
</html>
"""

        # Attach both versions
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Send the email using SMTP
        # Try port 587 with STARTTLS first (most common)
        try:
            server = smtplib.SMTP(smtp_server, 587, timeout=10)
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, global_admin.email, msg.as_string())
            server.quit()
            logger.info("Sent new user notification email to global admin")
            return True
        except (smtplib.SMTPException, OSError) as exc:
            # If port 587 fails, try port 465 with SSL
            logger.warning(
                "Port 587 (STARTTLS) failed for new user notification, trying port 465 (SSL): %s",
                exc,
            )
            try:
                server = smtplib.SMTP_SSL(smtp_server, 465, timeout=10)
                server.login(from_email, password)
                server.sendmail(from_email, global_admin.email, msg.as_string())
                server.quit()
                logger.info("Sent new user notification email to global admin via SSL")
                return True
            except (smtplib.SMTPException, OSError) as exc2:
                logger.error(
                    "Failed to send new user notification via both ports: %s",
                    exc2,
                )
                return False

    except Exception as exc:
        logger.exception("Unexpected error sending new user notification")
        return False


def send_account_activation_notification(user_name, user_email):
    """
    Send an email notification to a user when their account is activated.

    Args:
        user_name: Name of the user whose account was activated
        user_email: Email of the user whose account was activated

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Get global email settings
        email_settings = GlobalEmailSettings.query.first()

        if not email_settings:
            logger.warning("No global email settings configured, skipping activation notification")
            return False

        # Extract email credentials from global settings
        from_email = email_settings.email
        password = decrypt_password(email_settings.password)
        smtp_server = email_settings.smtp_server

        # Create the email message
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = user_email
        msg['Subject'] = 'Your PyCashFlow Account Has Been Activated'

        # Create plain text version
        text_content = f"""
Hello {user_name},

Great news! Your PyCashFlow account has been activated and you can now log in.

You can access your account at any time by visiting the login page.

If you have any questions or need assistance, please contact your administrator.

Best regards,
The PyCashFlow Team
"""

        # Create HTML version
        html_content = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
      <h2 style="color: #10b981; border-bottom: 3px solid #10b981; padding-bottom: 10px;">
        Account Activated!
      </h2>
      <p>Hello <strong>{user_name}</strong>,</p>
      <p>Great news! Your PyCashFlow account has been activated and you can now log in.</p>

      <div style="background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;">
          <strong>What's next?</strong><br>
          You can now access all features of PyCashFlow including:
        </p>
        <ul style="margin: 10px 0;">
          <li>Cash flow forecasting</li>
          <li>Schedule management</li>
          <li>Balance tracking</li>
          <li>And more!</li>
        </ul>
      </div>

      <p>If you have any questions or need assistance, please contact your administrator.</p>

      <p style="margin-top: 30px;">
        Best regards,<br>
        <strong>The PyCashFlow Team</strong>
      </p>
    </div>
  </body>
</html>
"""

        # Attach both versions
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Send the email using SMTP
        # Try port 587 with STARTTLS first (most common)
        try:
            server = smtplib.SMTP(smtp_server, 587, timeout=10)
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, user_email, msg.as_string())
            server.quit()
            logger.info("Sent account activation email successfully")
            return True
        except (smtplib.SMTPException, OSError) as exc:
            # If port 587 fails, try port 465 with SSL
            logger.warning(
                "Port 587 (STARTTLS) failed for activation notification, trying port 465 (SSL): %s",
                exc,
            )
            try:
                server = smtplib.SMTP_SSL(smtp_server, 465, timeout=10)
                server.login(from_email, password)
                server.sendmail(from_email, user_email, msg.as_string())
                server.quit()
                logger.info("Sent account activation email successfully via SSL")
                return True
            except (smtplib.SMTPException, OSError) as exc2:
                logger.error(
                    "Failed to send activation notification via both ports: %s",
                    exc2,
                )
                return False

    except Exception as exc:
        logger.exception("Unexpected error sending activation notification")
        return False


def send_password_setup_email(user_name, user_email, setup_url, expires_minutes):
    """Send password setup email for payment-created cloud users."""
    try:
        email_settings = GlobalEmailSettings.query.first()
        if not email_settings:
            logger.warning("No global email settings configured, skipping password setup email")
            return False

        from_email = email_settings.email
        password = decrypt_password(email_settings.password)
        smtp_server = email_settings.smtp_server
        support_contact = current_app.config.get("SUPPORT_CONTACT_EMAIL") or from_email

        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = user_email
        msg['Subject'] = 'Set Your PyCashFlow Password'

        text_content = f"""
Hello {user_name},

Your PyCashFlow Cloud account was created.

Please set your password using this secure one-time link:
{setup_url}

This link expires in {expires_minutes} minutes and can only be used once.
If you did not expect this email or need help, contact {support_contact}.

Best regards,
The PyCashFlow Team
"""
        part1 = MIMEText(text_content, 'plain')
        msg.attach(part1)

        try:
            server = smtplib.SMTP(smtp_server, 587, timeout=10)
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, user_email, msg.as_string())
            server.quit()
            logger.info("Sent password setup email user_id_email=%s", user_email)
            return True
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning(
                "Port 587 (STARTTLS) failed for password setup email, trying port 465 (SSL): %s",
                exc,
            )
            try:
                server = smtplib.SMTP_SSL(smtp_server, 465, timeout=10)
                server.login(from_email, password)
                server.sendmail(from_email, user_email, msg.as_string())
                server.quit()
                logger.info("Sent password setup email via SSL user_email=%s", user_email)
                return True
            except (smtplib.SMTPException, OSError) as exc2:
                logger.error("Failed password setup email via both ports: %s", exc2)
                return False
    except Exception:
        logger.exception("Unexpected error sending password setup email")
        return False


# Allow script to be run standalone from cron
if __name__ == "__main__":
    from app import create_app

    log_path = os.getenv("GETEMAIL_LOG_FILE")
    if log_path:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            handlers = [logging.FileHandler(log_path)]
        except OSError as exc:
            handlers = [logging.StreamHandler(sys.stdout)]
            print(f"WARNING: Could not open log file {log_path}: {exc}; falling back to stdout", file=sys.stderr)
    else:
        handlers = [logging.StreamHandler(sys.stdout)]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )
    logger.info("Starting email balance import...")
    app = create_app()

    with app.app_context():
        try:
            process_email_balances()
            logger.info("Email balance import completed successfully")
        except Exception as exc:
            logger.exception("Email balance import failed")
            sys.exit(1)
