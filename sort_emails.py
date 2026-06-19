#!/usr/bin/env python3
"""
Al Safeenah Email Sorter — Cloud Automated Version
Uses Zoho Mail REST API + Claude AI for classification.

GitHub Secrets required:
  ANTHROPIC_API_KEY   — Anthropic API key
  ZOHO_CLIENT_ID      — Zoho Self Client ID
  ZOHO_CLIENT_SECRET  — Zoho Self Client Secret
  ZOHO_REFRESH_TOKEN  — Zoho OAuth Refresh Token
"""

import json, logging, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from collections import defaultdict

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
INBOX_ID      = "2108081000000008014"
ZOHO_AUTH_URL = "https://accounts.zoho.com/oauth/v2/token"
ZOHO_API_BASE = "https://mail.zoho.com/api"

FOLDERS = {
    "Business Critical":  "2108081000002144001",
    "Suppliers":          "2108081000002145001",
    "Job Applications":   "2108081000002146001",
    "Payment Remittance": "2108081000002147001",
    "Government":         "2108081000002148001",
    "Operational":        "2108081000002148002",
    "Spam":               "2108081000000008024",
}

# ── Zoho API Helpers ──────────────────────────────────────────────────────────

def get_access_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(ZOHO_AUTH_URL, data=data, method="POST")
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    if "access_token" not in result:
        raise RuntimeError(f"Token exchange failed: {result}")
    return result["access_token"]


def zoho_get(url, token):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Zoho-oauthtoken {token}"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} — {body}")


def zoho_post(url, token, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} — {body}")


def get_account_id(token):
    """Fetch account ID live from Zoho instead of hardcoding."""
    result = zoho_get(f"{ZOHO_API_BASE}/accounts", token)
    accounts = result.get("data", [])
    if not accounts:
        raise RuntimeError(f"No Zoho accounts found. Full response: {result}")
    account_id = accounts[0].get("accountId")
    log.info(f"📬  Zoho account ID: {account_id}")
    return account_id


def fetch_inbox_emails(token, account_id):
    url = (
        f"{ZOHO_API_BASE}/accounts/{account_id}/messages/view"
        f"?folderId={INBOX_ID}&limit=100&status=all"
    )
    return zoho_get(url, token).get("data", [])


def move_email_batch(token, account_id, message_ids, destination_folder_id):
    url = f"{ZOHO_API_BASE}/accounts/{account_id}/updatemessage"
    return zoho_post(url, token, {
        "messageId": message_ids,
        "folderId":  destination_folder_id,
        "mode":      "move",
    })


# ── Claude Classification ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You classify emails for Al Safeenah Engineering Services LLC — a CNC machine shop in Dubai, UAE.
Services: CNC turning, CNC milling, manual lathe/milling, welding, fitting/fabrication.
Clients: oil & gas, construction, marine.

Assign each email to exactly ONE folder from this list:
  Business Critical | Suppliers | Job Applications | Payment Remittance
  Government | Operational | Spam | SKIP

Priority rules (first match wins):

SKIP:
  - Auto-replies, out-of-office, bounced sent mail from @alsafeenah.ae

Spam:
  - Products irrelevant to CNC shop: curtains, furniture, insulation, adhesives, cleaning, printing/signage
  - Cold IT/digital: website design, SEO, PPC, social media, app development, IT support
  - Cold financial/legal: business loans, insurance, unsolicited accounting/tax/trademark
  - Tender platform spam: UAE Business Gate, UAE Tenders Platform, GCC Chambers
  - Chinese factory mass-marketing with no prior relationship
  - Scams, phishing, fake orders from unknown parties
  - Mass manpower recruitment with no specific role

Payment Remittance:
  - Subject has: remittance, payment advice, payment confirmation

Government:
  - Sender: pcfc.ae, government authority, municipality, ministry, chamber of commerce
  - Subject: circular, regulatory, compliance, e-invoicing, VAT, trade licence

Job Applications:
  - CV, resume, vacancy, career, applying for, looking for job, seeking employment
  - Recruitment agency referencing a specific role

Suppliers:
  - Relevant engineering supplier: cutting tools, steel/metal, raw materials, calibration, EDM wire
  - Known brands: Guehring, Sandvik, Kennametal, Iscar, Ceratizit, Seco, Mitsubishi, TruCut
  - NOT curtains/software/SEO (those are Spam)

Operational:
  - Sender domain: zoho.com, microsoft.com, yellowpages-uae.net
  - System alerts, login notifications, logistics updates, internal @alsafeenah.ae emails

Business Critical (DEFAULT for genuine client/project emails):
  - RFQ, enquiry, inquiry, request for quotation, please quote, tender
  - Machining keywords: gear, roller, shaft, flange, bushing, bearing, coupling, pipe spool,
    fabrication, CNC, lathe, milling, welding, fitting, rebar coupler, bollard, hydraulic
  - Active client threads, POs, delivery notes, invoices related to a job
  - WHEN IN DOUBT always choose Business Critical

Return ONLY a valid JSON array, no explanation, no markdown:
[{"messageId": "...", "folder": "Folder Name"}, ...]
"""


def classify_emails(emails, api_key):
    if not emails:
        return []

    lines = []
    for e in emails:
        lines.append(
            f"ID: {e.get('messageId')}\n"
            f"From: {e.get('fromAddress', '')}\n"
            f"Subject: {e.get('subject', '(no subject)')}\n"
            f"Summary: {e.get('summary', '')}\n"
        )
    user_message = "Classify these emails:\n\n" + "\n---\n".join(lines)

    body = json.dumps({
        "model":      "claude-sonnet-4-6",
        "max_tokens": 4096,
        "system":     SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": user_message}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body, method="POST",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req) as r:
        response = json.loads(r.read())

    text = "".join(
        b.get("text", "") for b in response.get("content", [])
        if b.get("type") == "text"
    ).strip()

    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key       = os.environ.get("ANTHROPIC_API_KEY")
    client_id     = os.environ.get("ZOHO_CLIENT_ID")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
    refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")

    for name, val in [
        ("ANTHROPIC_API_KEY",  api_key),
        ("ZOHO_CLIENT_ID",     client_id),
        ("ZOHO_CLIENT_SECRET", client_secret),
        ("ZOHO_REFRESH_TOKEN", refresh_token),
    ]:
        if not val:
            log.error(f"{name} is not set.")
            sys.exit(1)

    log.info("🚀  Al Safeenah Email Sorter starting...")
    log.info(f"📅  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # 1. Zoho access token
    log.info("🔑  Getting Zoho access token...")
    try:
        token = get_access_token(client_id, client_secret, refresh_token)
        log.info("✅  Access token obtained.")
    except Exception as e:
        log.error(f"Zoho auth failed: {e}")
        sys.exit(1)

    # 2. Get account ID dynamically
    log.info("🔍  Fetching Zoho account ID...")
    try:
        account_id = get_account_id(token)
    except Exception as e:
        log.error(f"Failed to get account ID: {e}")
        sys.exit(1)

    # 3. Fetch inbox
    log.info("📥  Fetching inbox emails...")
    try:
        emails = fetch_inbox_emails(token, account_id)
        log.info(f"📧  {len(emails)} emails found in inbox.")
    except Exception as e:
        log.error(f"Failed to fetch emails: {e}")
        sys.exit(1)

    if not emails:
        print("\n✅  Inbox is already empty — nothing to sort.\n")
        return

    # 4. Classify
    log.info("🤖  Classifying with Claude...")
    try:
        classifications = classify_emails(emails, api_key)
        log.info(f"✅  {len(classifications)} emails classified.")
    except Exception as e:
        log.error(f"Classification failed: {e}")
        sys.exit(1)

    # 5. Group by folder and move
    folder_groups = defaultdict(list)
    skip_count    = 0

    for item in classifications:
        folder = item.get("folder", "SKIP")
        if folder == "SKIP" or folder not in FOLDERS:
            skip_count += 1
            continue
        folder_groups[folder].append(item["messageId"])

    moved_total   = 0
    folder_counts = {}
    bc_highlights = []

    for folder_name, ids in folder_groups.items():
        folder_id = FOLDERS[folder_name]
        log.info(f"📂  Moving {len(ids)} → {folder_name}...")
        for i in range(0, len(ids), 10):
            batch = ids[i:i+10]
            try:
                move_email_batch(token, account_id, batch, folder_id)
                moved_total += len(batch)
                folder_counts[folder_name] = folder_counts.get(folder_name, 0) + len(batch)
            except Exception as e:
                log.warning(f"Move batch failed ({folder_name}): {e}")

        if folder_name == "Business Critical":
            for mid in ids:
                for e in emails:
                    if e.get("messageId") == mid:
                        bc_highlights.append(
                            f"  🟢 {e.get('subject','(no subject)')} — {e.get('fromAddress','')}"
                        )
                        break

    # 6. Summary
    print("\n" + "=" * 56)
    print("📬  EMAIL SORT COMPLETE — Al Safeenah Engineering")
    print("=" * 56)
    print(f"Run time       : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Emails scanned : {len(emails)}")
    print(f"Emails moved   : {moved_total}")
    print(f"Left in inbox  : {len(emails) - moved_total}")
    print()
    for folder_name, count in folder_counts.items():
        print(f"  📂 {folder_name:<22} → {count}")
    if bc_highlights:
        print("\n  Business Critical highlights:")
        for line in bc_highlights[:5]:
            print(line)
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
