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
from datetime import datetime
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
            messages = int(messages[0])

            email_content = {}

            # INNER LOOP: Process all emails in THIS user's inbox
            for i in range(1, messages + 1):
                try:
                    res, msg = imap.fetch(str(i), "(RFC822)")
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
