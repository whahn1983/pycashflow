import sqlite3
import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime


# connect to the database for email information
basedir = os.path.abspath(os.path.dirname(__file__))
sql_database = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data/db.sqlite')
sql_database = sql_database[10:]

conn = sqlite3.connect(sql_database)

# OUTER LOOP: Get all users with email settings configured
cursor = conn.execute("""
    SELECT u.id, e.email, e.password, e.server, e.subjectstr, e.startstr, e.endstr
    FROM user u
    INNER JOIN email e ON u.id = e.user_id
""")

for user_row in cursor:
    user_id = user_row[0]
    username = user_row[1]
    password = user_row[2]
    imap_server = user_row[3]
    subjectstr = user_row[4]
    startstr = user_row[5]
    endstr = user_row[6]

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

            # Insert balance WITH user_id
            conn.execute(
                "INSERT INTO BALANCE (AMOUNT, DATE, USER_ID) VALUES (?,?,?)",
                (str(new_balance), datetime.today().date(), user_id)
            )
            conn.commit()
        except:
            pass  # No balance found in emails for this user

        # Close IMAP connection for THIS user
        imap.close()
        imap.logout()

    except Exception as e:
        # Failed to connect to IMAP for this user - skip to next user
        print(f"Failed to process emails for user {user_id}: {e}")
        continue

# Close database connection after processing ALL users
conn.close()
