#!/usr/bin/env python3
"""
Al Safeenah Email Sorter — Cloud Automated Version
Gets a fresh Zoho OAuth token, then lets Claude sort
emails autonomously via Zoho Mail MCP.

GitHub Secrets required:
  ANTHROPIC_API_KEY   — Anthropic API key
  ZOHO_CLIENT_ID      — Zoho Self Client ID
  ZOHO_CLIENT_SECRET  — Zoho Self Client Secret
  ZOHO_REFRESH_TOKEN  — Zoho OAuth Refresh Token
"""

import anthropic
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Zoho MCP server URL ───────────────────────────────────────────────────────
ZOHO_MCP_URL  = "https://mail-organization-925547323.zohomcp.com/mcp/86af220a36b74244778fa84a90439606/message"
ZOHO_AUTH_URL = "https://accounts.zoho.com/oauth/v2/token"

# ── Email Sorter Instructions ─────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are the automated email sorter for Al Safeenah Engineering Services LLC,
a CNC machine shop based in Dubai, UAE (www.alsafeenah.ae).
Capabilities: CNC turning, CNC milling, manual lathe, manual milling, welding, fitting/fabrication.
Clients: oil & gas, construction, marine sectors.

Sort ALL inbox emails into the correct folders by following the steps below exactly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOLDER MAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Folder Name         | Folder ID
--------------------|---------------------
Business Critical   | 2108081000002144001
Suppliers           | 2108081000002145001
Job Applications    | 2108081000002146001
Payment Remittance  | 2108081000002147001
Government          | 2108081000002148001
Operational         | 2108081000002148002
Spam                | 2108081000000008024
Inbox (source)      | 2108081000000008014

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — GET ACCOUNT ID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call ZohoMail_getMailAccounts. Extract accountId from the first account.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — FETCH INBOX EMAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call ZohoMail_listEmails with:
  accountId  : <from step 1>
  folderId   : 2108081000000008014
  limit      : 100
  status     : all

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — CLASSIFY EACH EMAIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Apply rules in priority order. First match wins.

SKIP (do not move):
  - Already not in Inbox (folderId ≠ 2108081000000008014)
  - Auto-reply / out-of-office

Spam:
  - Products irrelevant to CNC shop: curtains, furniture, insulation, cleaning, signage
  - Cold IT/digital: SEO, website design, app development, IT support
  - Cold financial: business loans, insurance, unsolicited accounting/tax
  - Tender platform spam: UAE Business Gate, UAE Tenders Platform
  - Chinese factory mass-marketing with no prior relationship
  - Scams, phishing, fake orders from unknown parties
  - Mass manpower spam with no specific role

Payment Remittance:
  - Subject: "remittance", "payment advice", "payment confirmation"

Government:
  - Sender: pcfc.ae, government authority, municipality, ministry
  - Subject: "circular", "regulatory", "e-invoicing", "VAT", "trade licence"

Job Applications:
  - CV, resume, vacancy, career, applying for, seeking employment
  - Recruitment agency with a specific role

Suppliers:
  - Relevant engineering supplier: cutting tools, steel, raw materials, calibration
  - Known brands: Guehring, Sandvik, Kennametal, Iscar, Ceratizit, Seco, TruCut

Operational:
  - Sender: zoho.com, microsoft.com, yellowpages-uae.net
  - System alerts, login notifications, logistics, internal @alsafeenah.ae

Business Critical (DEFAULT — when in doubt, always use this):
  - RFQ, enquiry, inquiry, quotation, please quote, tender
  - Machining keywords: gear, roller, shaft, flange, bushing, bearing, coupling,
    pipe spool, CNC, lathe, milling, welding, fitting, rebar coupler, bollard, hydraulic
  - Active client threads, POs, delivery notes, invoices, MTC requests

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — MOVE EACH EMAIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For each classified email (not SKIP), call ZohoMail_moveMessages with:
  accountId          : <from step 1>
  messageId          : <email messageId>
  currentFolderId    : 2108081000000008014
  destinationFolderId: <target folder ID>

If a move fails, log it and continue — do not stop.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5 — REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Print a summary showing:
- Total emails scanned and moved
- Count per folder
- Top 5 Business Critical emails (subject + sender)
"""


def get_access_token(client_id, client_secret, refresh_token):
    """Exchange refresh token for a fresh Zoho access token."""
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


def main():
    # ── Validate env vars ─────────────────────────────────────────────────────
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

    # ── Get fresh Zoho OAuth token ────────────────────────────────────────────
    log.info("🔑  Getting Zoho access token...")
    try:
        access_token = get_access_token(client_id, client_secret, refresh_token)
        log.info("✅  Access token obtained.")
    except Exception as e:
        log.error(f"Zoho auth failed: {e}")
        sys.exit(1)

    # ── Call Claude with Zoho MCP ─────────────────────────────────────────────
    log.info("📡  Calling Claude with Zoho Mail MCP — sorting in progress...")
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.beta.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Please sort the inbox now. Fetch all inbox emails, "
                    "classify each one, move them to the correct folders, "
                    "and provide the full summary report when done."
                )
            }],
            mcp_servers=[{
                "type":                "url",
                "url":                 ZOHO_MCP_URL,
                "name":                "zoho-mail",
                "authorization_token": access_token,
            }],
            betas=["mcp-client-2025-04-04"],
        )

        # ── Print summary ─────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        for block in response.content:
            if hasattr(block, "text"):
                print(block.text)
        print("=" * 60 + "\n")

        log.info(f"✅  Done. Stop reason: {response.stop_reason}")
        log.info(
            f"🔢  Tokens — input: {response.usage.input_tokens} | "
            f"output: {response.usage.output_tokens}"
        )

    except anthropic.APIConnectionError as e:
        log.error(f"Connection error: {e}")
        sys.exit(1)
    except anthropic.RateLimitError:
        log.error("Rate limit exceeded.")
        sys.exit(1)
    except anthropic.APIStatusError as e:
        log.error(f"API error {e.status_code}: {e.message}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
