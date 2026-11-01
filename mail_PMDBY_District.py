from pathlib import Path
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import mimetypes
import os


# ============================================================
# CONFIGURATION
# ============================================================

DOWNLOAD_DIR = Path("data")

# Gmail sender
SENDER_EMAIL = os.environ["SENDER_EMAIL"]

# Gmail App Password
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"]

# Recipient
RECIPIENT_EMAILS = [
    "akshay.shirsat.2307@gmail.com"
]


# ============================================================
# YESTERDAY DATE
# ============================================================

yesterday = datetime.now() - timedelta(days=0)

date_str = yesterday.strftime("%Y%m%d")

date_display = yesterday.strftime("%d-%m-%Y")


print("======================================")
print("PMFBY EMAIL")
print("======================================")

print(
    "Looking for files containing date:",
    date_str
)


# ============================================================
# FIND ALL YESTERDAY FILES
# ============================================================

attachments = []

for filepath in DOWNLOAD_DIR.iterdir():

    if not filepath.is_file():
        continue

    # Check whether yesterday's date is present
    # anywhere in the filename

    if date_str in filepath.name:

        attachments.append(
            filepath
        )


# Sort files alphabetically
attachments.sort()


# ============================================================
# DISPLAY FILES
# ============================================================

print(
    "\nFiles found:"
)

for filepath in attachments:

    print(
        " -",
        filepath.name
    )


# ============================================================
# STOP IF NO FILES FOUND
# ============================================================

if not attachments:

    raise FileNotFoundError(

        f"No files containing "
        f"{date_str} were found in "
        f"{DOWNLOAD_DIR}"

    )


# ============================================================
# CREATE EMAIL
# ============================================================

msg = EmailMessage()


msg["Subject"] = (

    f"IMD Daily Rainfall Data - "
    f"{date_display}"

)


msg["From"] = SENDER_EMAIL


msg["To"] = ", ".join(
    RECIPIENT_EMAILS
)


# ============================================================
# EMAIL BODY
# ============================================================

body = f"""
Dear Sir/Madam,

Please find attached the IMD daily rainfall data
for {date_display}.

Files attached:

"""

for filepath in attachments:

    body += (
        f"- {filepath.name}\n"
    )


body += f"""

Data Date: {date_display}

Regards,
Akshay
"""


msg.set_content(
    body
)


# ============================================================
# ATTACH FILES
# ============================================================

for filepath in attachments:

    mime_type, _ = mimetypes.guess_type(
        filepath
    )

    if mime_type is None:

        mime_type = (
            "application/octet-stream"
        )


    maintype, subtype = (
        mime_type.split(
            "/",
            1
        )
    )


    with open(
        filepath,
        "rb"
    ) as f:

        file_data = f.read()


    msg.add_attachment(

        file_data,

        maintype=maintype,

        subtype=subtype,

        filename=filepath.name

    )


    print(
        "Attached:",
        filepath.name
    )


# ============================================================
# SEND EMAIL
# ============================================================

print(
    "\nConnecting to Gmail..."
)


with smtplib.SMTP_SSL(

    "smtp.gmail.com",

    465

) as smtp:

    smtp.login(

        SENDER_EMAIL,

        SENDER_PASSWORD

    )


    smtp.send_message(
        msg
    )


# ============================================================
# SUCCESS
# ============================================================

print(
    "\n======================================"
)

print(
    "EMAIL SENT SUCCESSFULLY"
)

print(
    "======================================"
)

print(
    "Date:",
    date_display
)

print(
    "Files attached:",
    len(attachments)
)

for filepath in attachments:

    print(
        " -",
        filepath.name
    )
