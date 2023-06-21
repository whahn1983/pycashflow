import sqlite3
import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime


# connect to the database for email information
basedir = os.path.abspath(os.path.dirname(__file__))
sql_database = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'db.sqlite')
sql_database = sql_database[10:]

conn = sqlite3.connect(sql_database)

cursor = conn.execute("SELECT email, password, server from email")

for row in cursor:
    username = row[0]
    password = row[1]
    imap_server = row[2]

# create an IMAP4 class with SSL
imap = imaplib.IMAP4_SSL(imap_server)
# authenticate
imap.login(username, password)

status, messages = imap.select("INBOX", readonly=True)
messages = int(messages[0])

email_content = {}

for i in range(1, messages + 1):
    # fetch the email message by ID
    try:
        res, msg = imap.fetch(str(i), "(RFC822)")
        for response in msg:
            if isinstance(response, tuple):
                # parse a bytes email into a message object
                msg = email.message_from_bytes(response[1])
                # decode the email subject
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    # if it's a bytes, decode to str
                    try:
                        subject = subject.decode(encoding)
                    except:
                        subject = "subject"
                # decode email sender
                From, encoding = decode_header(msg.get("From"))[0]
                if isinstance(From, bytes):
                    try:
                        From = From.decode(encoding)
                    except:
                        pass
                # if the email message is multipart
                if msg.is_multipart():
                    # iterate over email parts
                    for part in msg.walk():
                        # extract content type of email
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        try:
                            # get the email body
                            body = part.get_payload(decode=True).decode()
                        except:
                            pass
                        if content_type == "text/plain" and "attachment" not in content_disposition:
                            # print text/plain emails and skip attachments
                            try:
                                email_content[subject] = body
                            except:
                                pass
                else:
                    # extract content type of email
                    content_type = msg.get_content_type()
                    # get the email body
                    body = msg.get_payload(decode=True).decode()
                    if content_type == "text/plain":
                        # print only text email parts
                        try:
                            email_content[subject] = body
                        except:
                            pass
    except:
        pass

# formatted for Bank of America email alerts.  Re-format for your bank.
try:
    start_index = email_content['Your Available Balance'].find('Balance: ') + 10
    end_index = email_content['Your Available Balance'].find(' \r\nAccount: ')
    new_balance = float(email_content['Your Available Balance'][start_index:end_index].replace(',', ''))

    conn.execute("INSERT INTO BALANCE (AMOUNT, DATE) VALUES (?,?)", (str(new_balance), datetime.today().date()))
    conn.commit()
except:
    pass

# close the connection and logout
imap.close()
imap.logout()
conn.close()
