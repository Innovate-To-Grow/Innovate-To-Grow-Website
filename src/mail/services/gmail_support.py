import base64
import json
import mimetypes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import bleach
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
ALLOWED_TAGS = [
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target"],
    "img": ["src", "alt", "width", "height", "style"],
    "div": ["style", "class"],
    "span": ["style", "class"],
    "p": ["style", "class"],
    "td": ["style", "colspan", "rowspan"],
    "th": ["style", "colspan", "rowspan"],
    "table": ["style", "class", "cellpadding", "cellspacing", "border", "width"],
    "tr": ["style"],
    "h1": ["style"],
    "h2": ["style"],
    "h3": ["style"],
    "blockquote": ["style", "class"],
}


def build_service(account):
    credentials_info = json.loads(account.service_account_json)
    credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    delegated_credentials = credentials.with_subject(account.email)
    return build("gmail", "v1", credentials=delegated_credentials, cache_discovery=False)


def list_message_summaries(service, *, q="", label_ids=None, max_results=25, page_token=None, logger=None):
    kwargs = {"userId": "me", "maxResults": max_results}
    if q:
        kwargs["q"] = q
    if label_ids:
        kwargs["labelIds"] = label_ids
    if page_token:
        kwargs["pageToken"] = page_token

    response = service.users().messages().list(**kwargs).execute()
    messages = response.get("messages", [])
    next_page_token = response.get("nextPageToken")
    if not messages:
        return {"messages": [], "next_page_token": next_page_token}

    fetched = {}

    def on_message_response(request_id, resp, exc):
        if exc is not None:
            if logger:
                logger.warning("Batch get failed for message %s: %s", request_id, exc)
            return
        fetched[request_id] = resp

    batch = service.new_batch_http_request(callback=on_message_response)
    for msg_stub in messages:
        batch.add(
            service.users().messages().get(userId="me", id=msg_stub["id"], format="metadata"), request_id=msg_stub["id"]
        )
    batch.execute()

    summaries = []
    for msg_stub in messages:
        msg = fetched.get(msg_stub["id"])
        if msg is None:
            continue
        summaries.append(
            {
                "id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "snippet": msg.get("snippet", ""),
                "label_ids": msg.get("labelIds", []),
                "is_unread": "UNREAD" in msg.get("labelIds", []),
                **parse_headers(msg),
            }
        )

    return {"messages": summaries, "next_page_token": next_page_token}


def parse_headers(msg):
    result = {"from": "", "to": "", "cc": "", "subject": "", "date": "", "message_id": ""}
    header_map = {
        "From": "from",
        "To": "to",
        "Cc": "cc",
        "Subject": "subject",
        "Date": "date",
        "Message-ID": "message_id",
        "Message-Id": "message_id",
    }
    for header in msg.get("payload", {}).get("headers", []):
        key = header_map.get(header["name"])
        if key:
            result[key] = header["value"]
    return result


def extract_body(payload):
    mime_type = payload.get("mimeType", "")
    if mime_type in {"text/html", "text/plain"}:
        data = payload.get("body", {}).get("data", "")
        content = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace") if data else ""
        return (content, "") if mime_type == "text/html" else ("", content)
    html_body, plain_body = "", ""
    for part in payload.get("parts", []):
        html_part, plain_part = extract_body(part)
        html_body = html_part or html_body
        plain_body = plain_part or plain_body
    return html_body, plain_body


def extract_attachments(payload):
    attachments = []
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if filename and attachment_id:
            attachments.append(
                {
                    "filename": filename,
                    "attachment_id": attachment_id,
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "size": body.get("size", 0),
                }
            )
        attachments.extend(extract_attachments(part))
    return attachments


def sanitize_html(html):
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)


def build_mime_message(
    account, *, to, subject, body_html, cc="", bcc="", attachments=None, in_reply_to=None, references=None
):
    msg = MIMEMultipart("mixed" if attachments else "alternative")
    msg.attach(MIMEText(body_html, "html"))
    for filename, content_bytes in attachments or []:
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)
        attachment = MIMEBase(maintype, subtype)
        attachment.set_payload(content_bytes)
        from email import encoders

        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(attachment)

    msg["to"] = to
    msg["subject"] = subject
    msg["from"] = f"{account.display_name} <{account.email}>" if account.display_name else account.email
    if cc:
        msg["cc"] = cc
    if bcc:
        msg["bcc"] = bcc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    return msg
