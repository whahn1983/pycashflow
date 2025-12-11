#!/usr/bin/env python3
"""
Email balance import script for pycashflow.
Processes IMAP email inboxes to extract and import balance information.

This script can be run standalone from cron or called from within the application.
"""
import os
import sys

# When run as standalone script, add parent directory to path for imports
# This allows 'from app import ...' to work when called from cron
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import imaplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from datetime import datetime, timedelta
from app import db
from app.models import User, Email, Balance


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

    for user, email_config in users_with_email:
        user_id = user.id
        username = email_config.email
        password = email_config.password
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

            print(f"Found {len(email_ids)} email(s) from the past day for user {user_id}")

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
                                except:
                                    subject = "subject"

                            # Decode sender
                            From, encoding = decode_header(msg.get("From"))[0]
                            if isinstance(From, bytes):
                                try:
                                    From = From.decode(encoding)
                                except:
                                    pass

                            # Extract email body
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))
                                    try:
                                        body = part.get_payload(decode=True).decode()
                                    except:
                                        pass
                                    if content_type == "text/plain" and "attachment" not in content_disposition:
                                        try:
                                            email_content[subject] = body
                                        except:
                                            pass
                            else:
                                content_type = msg.get_content_type()
                                body = msg.get_payload(decode=True).decode()
                                if content_type == "text/plain":
                                    try:
                                        email_content[subject] = body
                                    except:
                                        pass
                except:
                    pass  # Skip individual email errors

            # Extract balance from emails for THIS user
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
                print(f"Successfully imported balance ${new_balance} for user {user_id}")
            except KeyError:
                # No email with the specified subject found
                pass
            except Exception as e:
                # No balance found in emails for this user
                print(f"Could not extract balance for user {user_id}: {e}")

            # Close IMAP connection for THIS user
            imap.close()
            imap.logout()

        except Exception as e:
            # Failed to connect to IMAP for this user - skip to next user
            print(f"Failed to process emails for user {user_id}: {e}")
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
            print("No global admin found, skipping notification")
            return False

        # Get email settings for the global admin
        email_config = Email.query.filter_by(user_id=global_admin.id).first()

        if not email_config:
            print(f"No email settings configured for global admin {global_admin.id}, skipping notification")
            return False

        # Extract email credentials
        from_email = email_config.email
        password = email_config.password
        imap_server = email_config.server

        # Convert IMAP server to SMTP server
        # Common patterns: imap.gmail.com -> smtp.gmail.com, imap.mail.yahoo.com -> smtp.mail.yahoo.com
        smtp_server = imap_server.replace('imap', 'smtp')

        # Create the email message
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = from_email  # Send to the global admin's own email
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
            server.sendmail(from_email, from_email, msg.as_string())
            server.quit()
            print(f"Successfully sent new user notification email to {from_email}")
            return True
        except Exception as e:
            # If port 587 fails, try port 465 with SSL
            print(f"Failed to send via port 587, trying SSL on port 465: {e}")
            try:
                server = smtplib.SMTP_SSL(smtp_server, 465, timeout=10)
                server.login(from_email, password)
                server.sendmail(from_email, from_email, msg.as_string())
                server.quit()
                print(f"Successfully sent new user notification email to {from_email} via SSL")
                return True
            except Exception as e2:
                print(f"Failed to send email via both ports: {e2}")
                return False

    except Exception as e:
        print(f"Error sending new user notification: {e}")
        return False


# Allow script to be run standalone from cron
if __name__ == "__main__":
    from app import create_app

    print("Starting email balance import...")
    app = create_app()

    with app.app_context():
        try:
            process_email_balances()
            print("Email balance import completed successfully")
        except Exception as e:
            print(f"Email balance import failed: {e}")
            sys.exit(1)
