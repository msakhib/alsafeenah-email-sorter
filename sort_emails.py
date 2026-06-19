#!/usr/bin/env python3
"""
Al Safeenah Email Sorter — Cloud Automated Version
Zoho Mail REST API + Claude AI for classification.
Classification rules are loaded live from email_sorter_skill.md in this repo.

GitHub Secrets required:
  ANTHROPIC_API_KEY   — Anthropic API key
  ZOHO_CLIENT_ID      — Zoho Self Client ID
  ZOHO_CLIENT_SECRET  — Zoho Self Client Secret
  ZOHO_REFRESH_TOKEN  — Zoho OAuth Refresh Token
"""

import json, logging, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

INBOX_ID      = "2108081000000008014"
ZOHO_AUTH_URL = "https://accounts.zoho.com/oauth/v2/token"
ZOHO_API_BASE = "https://mail.zoho.com/api"
SKILL_FILE    = os.path.join(os.path.dirname(__file__), "email_sorter_skill.md")

FOLDERS = {
    "Business Critical":  "2108081000002144001",
    "Suppliers":          "2108081000002145001",
    "Job Applications":   "2108081000002146001",
    "Payment Remittance": "2108081000002147001",
    "Government":         "2108081000002148001",
    "Operational":        "2108081000002148002",
    "Spam":               "2108081000000008024",
}

# ── Skill loader ──────────────────────────────────────────────────────────────

CLASSIFICATION_SUFFIX = """
---
IMPORTANT — CLOUD AUTOMATION MODE:
You are running as an automated script, not inside claude.ai.
Do NOT attempt to call any MCP tools (ZohoMail_listEmails, ZohoMail_moveMessages, etc.).
Simply apply the classification rules above to the emails listed and return your answer.

Return ONLY a valid JSON array — no explanation, no markdown, no preamble:
[{"messageId": "...", "folder": "Folder Name"}, ...]

Valid folder names: Business Critical, Suppliers, Job Applications,
Payment Remittance, Government, Operational, Spam, SKIP
"""

def load_skill():
    """Load classification rules live from email_sorter_skill.md."""
    if not os.path.exists(SKILL_FILE):
        raise RuntimeError(
            f"Skill file not found at: {SKILL_FILE}\n"
            "Add email_sorter_skill.md to the repo alongside sort_emails.py."
        )
    with open(SKILL_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    log.info(f"📋  Skill loaded ({len(content)} chars) from email_sorter_skill.md")
    return content + CLASSIFICATION_SUFFIX


# ── Zoho helpers ──────────────────────────────────────────────────────────────

def get_access_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token", "client_id": client_id,
        "client_secret": client_secret, "refresh_token": refresh_token,
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(ZOHO_AUTH_URL, data=data, method="POST")
    ) as r:
        result = json.loads(r.read())
    if "access_token" not in result:
        raise RuntimeError(f"Token exchange failed: {result}")
    return result["access_token"]


def zoho_request(url, token, payload=None, method="GET"):
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} [{method} {url}] — {body}")


def get_account_id(token):
    result = zoho_request(f"{ZOHO_API_BASE}/accounts", token)
    accounts = result.get("data", [])
    if not accounts:
        raise RuntimeError(f"No accounts found: {result}")
    return accounts[0].get("accountId")


def fetch_inbox_emails(token, account_id):
    url = (f"{ZOHO_API_BASE}/accounts/{account_id}/messages/view"
           f"?folderId={INBOX_ID}&limit=100&status=all")
    return zoho_request(url, token).get("data", [])


def move_email(token, account_id, message_id, destination_folder_id):
    url = f"{ZOHO_API_BASE}/accounts/{account_id}/updatemessage"
    return zoho_request(url, token, payload={
        "mode":         "moveMessage",
        "destfolderId": int(destination_folder_id),
        "messageId":    [int(message_id)],
    }, method="PUT")


# ── Claude classification ─────────────────────────────────────────────────────

def classify_emails(emails, api_key, skill_content):
    if not emails:
        return []
    lines = [
        f"ID: {e.get('messageId')}\nFrom: {e.get('fromAddress','')}\n"
        f"Subject: {e.get('subject','(no subject)')}\nSummary: {e.get('summary','')}"
        for e in emails
    ]
    body = json.dumps({
        "model": "claude-sonnet-4-6", "max_tokens": 4096,
        "system": skill_content,
        "messages": [{"role": "user", "content": "Classify these emails:\n\n" + "\n---\n".join(lines)}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req) as r:
        response = json.loads(r.read())
    text = "".join(b.get("text","") for b in response.get("content",[]) if b.get("type")=="text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key       = os.environ.get("ANTHROPIC_API_KEY")
    client_id     = os.environ.get("ZOHO_CLIENT_ID")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
    refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")

    for name, val in [("ANTHROPIC_API_KEY", api_key), ("ZOHO_CLIENT_ID", client_id),
                      ("ZOHO_CLIENT_SECRET", client_secret), ("ZOHO_REFRESH_TOKEN", refresh_token)]:
        if not val:
            log.error(f"{name} is not set."); sys.exit(1)

    log.info("🚀  Al Safeenah Email Sorter starting...")
    log.info(f"📅  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # Load skill file
    try:
        skill_content = load_skill()
    except Exception as e:
        log.error(str(e)); sys.exit(1)

    log.info("🔑  Getting Zoho access token...")
    try:
        token = get_access_token(client_id, client_secret, refresh_token)
        log.info("✅  Token obtained.")
    except Exception as e:
        log.error(f"Auth failed: {e}"); sys.exit(1)

    log.info("🔍  Fetching account ID...")
    try:
        account_id = get_account_id(token)
        log.info(f"📬  Account ID: {account_id}")
    except Exception as e:
        log.error(f"Failed: {e}"); sys.exit(1)

    log.info("📥  Fetching inbox emails...")
    try:
        emails = fetch_inbox_emails(token, account_id)
        log.info(f"📧  {len(emails)} emails in inbox.")
    except Exception as e:
        log.error(f"Failed: {e}"); sys.exit(1)

    if not emails:
        print("\n✅  Inbox already empty.\n"); return

    log.info("🤖  Classifying with Claude (using live skill rules)...")
    try:
        classifications = classify_emails(emails, api_key, skill_content)
        log.info(f"✅  {len(classifications)} emails classified.")
    except Exception as e:
        log.error(f"Classification failed: {e}"); sys.exit(1)

    # Group by folder
    folder_groups = defaultdict(list)
    for item in classifications:
        folder = item.get("folder", "SKIP")
        if folder != "SKIP" and folder in FOLDERS:
            folder_groups[folder].append(item["messageId"])

    # Move emails
    moved_total   = 0
    folder_counts = {}
    bc_highlights = []

    for folder_name, ids in folder_groups.items():
        folder_id = FOLDERS[folder_name]
        log.info(f"📂  Moving {len(ids)} → {folder_name}...")
        for mid in ids:
            try:
                move_email(token, account_id, mid, folder_id)
                moved_total += 1
                folder_counts[folder_name] = folder_counts.get(folder_name, 0) + 1
            except Exception as e:
                log.warning(f"Could not move {mid}: {e}")

        if folder_name == "Business Critical":
            for mid in ids:
                for e in emails:
                    if e.get("messageId") == mid:
                        bc_highlights.append(
                            f"  🟢 {e.get('subject','(no subject)')} — {e.get('fromAddress','')}"
                        )
                        break

    # Summary
    print("\n" + "=" * 56)
    print("📬  EMAIL SORT COMPLETE — Al Safeenah Engineering")
    print("=" * 56)
    print(f"Run time       : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Emails scanned : {len(emails)}")
    print(f"Emails moved   : {moved_total}")
    print(f"Left in inbox  : {len(emails) - moved_total}")
    print()
    for fn, count in folder_counts.items():
        print(f"  📂 {fn:<22} → {count}")
    if bc_highlights:
        print("\n  Business Critical highlights:")
        for line in bc_highlights[:5]:
            print(line)
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
