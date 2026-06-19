---
name: email-sorter
description: >
  Sorts incoming emails from the Al Safeenah Zoho Mail inbox into the correct organised folders.
  Reads recent inbox emails, classifies each one, and moves it to the right folder: Business Critical
  (RFQs, active orders, project emails), Suppliers (vendor intros, tool/material suppliers),
  Job Applications (CVs, recruitment), Payment Remittance (payment advices), Government (PCFC,
  regulatory, compliance), Operational (system alerts, Zoho notifications, internal), or Spam
  (irrelevant cold marketing, Chinese product promotions, SEO pitches, loan offers, tender platform spam).
  Always use this skill when the user says: "sort my emails", "sort today's emails", "sort the inbox",
  "organise emails", "file emails into folders", "email sorting", "daily email sort", or any similar
  phrase about filing or organising inbox mail. Also trigger automatically when the user says
  "sort and check emails" or combines sorting with RFQ checking.
---

# Email Sorter — Al Safeenah Engineering

Classifies and moves inbox emails into the 7 organised folders for Al Safeenah Engineering.
Run this daily (or on demand) to keep the inbox clean and prioritised.

---

## Folder Map

| Folder Name | Folder ID | What goes here |
|---|---|---|
| Business Critical | 2108081000002144001 | RFQs, quotation requests, active orders, project comms, client follow-ups, PO acknowledgements |
| Suppliers | 2108081000002145001 | Vendor/supplier intros relevant to the shop, cutting tool newsletters, raw material offers |
| Job Applications | 2108081000002146001 | CV submissions, job applications, manpower recruitment agency emails |
| Payment Remittance | 2108081000002147001 | Remittance advices, payment confirmations, bank transfer notifications |
| Government | 2108081000002148001 | PCFC, regulatory circulars, compliance notices, e-invoicing, vendor registration from govt bodies |
| Operational | 2108081000002148002 | Zoho/system alerts, account security notifications, YellowPages leads, internal emails, logistics |
| Spam | 2108081000000008024 | Irrelevant cold marketing, Chinese product spam, SEO pitches, loan offers, tender platform spam |

> **Note:** If folder IDs ever change (e.g. after account reset), call `ZohoMail_getAllFolders` first
> and match folders by name to get fresh IDs.

---

## Workflow

### STEP 1 — Get Account

```tool
ZohoMail_getMailAccounts
```
Extract `accountId` from the first account (`2108081000000008002`). Store it for all subsequent calls.

---

### STEP 2 — Fetch Inbox Emails

```tool
ZohoMail_listEmails
  accountId: <accountId>
  folderId: 2108081000000008014   ← Inbox
  fields: subject,messageId,folderId,fromAddress,receivedTime,summary,hasAttachment
  limit: 100
  sortBy: date
  sortorder: false   ← newest first
  status: all
```

Default: fetch last 100 emails. If the user specifies "today's emails" or "last 24 hours", fetch all
and then filter in memory by `receivedTime` (compare timestamp to now − 86400000 ms).

---

### STEP 3 — Classify Each Email

For each email apply the classification rules below. Assign exactly ONE folder (or SKIP).

#### Classification Rules (apply in priority order — first match wins)

---

**A. SKIP — Leave in inbox (do not move)**

Skip if any of the following:
- Already not in the main Inbox folder (folderId ≠ `2108081000000008014`)
- Email is an auto-reply / out-of-office (subject contains "automatic reply", "out of office", "autoreply")
- Email is from `@alsafeenah.ae` sender **to** an external party (outbound sent mail that bounced back)

---

**B. Spam** ← clear junk, filter early

Move here if ANY of:
- Email is promoting products/services with no relevance to a CNC machine shop: curtains, insulation boards, adhesives/glue, furniture, office supplies, printed materials/signage, cleaning products
- Email is cold outreach for IT/software/digital services: website design, SEO audits, PPC/Google Ads, social media management, app development, software development, IT support, Microsoft 365/Google Workspace renewal pitches (from unknown vendors)
- Email is cold outreach for financial/legal services: business loans, credit facilities, insurance (not from an established provider), accounting audits (unsolicited), corporate tax filing (unsolicited), trademark registration
- Email is a repeated tender/platform registration invitation: UAE Business Gate, UAE Tenders Platform, GCC Chambers Federation, ADNOC vendor registration (mass-mailer style — not a direct PQ invitation)
- Email is Chinese factory mass-marketing not relevant to the shop: laser cutting machines (random sender), steel mass-marketing with no prior relationship, hydraulic parts promotions (random sender), piping systems promotions (random sender), freight/logistics cold outreach from Chinese companies
- Email is clearly a scam, phishing, or bulk order solicitation: "I am interested in your products, please send stock and price list", lottery/prize, domain name hijacking warnings, urgent "new order" from unknown party
- Sender is an advertising/printing/promotions company offering design or print services
- Email is recruitment spam: mass "we can source skilled manpower" emails from unknown agencies with no specific role

Do NOT move to Spam:
- Any email that could be a genuine client RFQ, even if the sender is unknown → Business Critical
- Recruitment agencies that reference a specific vacancy or skill (CNC operator, machinist) → Job Applications
- Supplier emails for relevant engineering products even if unsolicited → Suppliers

---

**C. Payment Remittance** ← check before Business Critical

Move here if ANY of:
- Subject contains: "remittance", "payment advice", "payment confirmation", "remittance advice", "FYI: remittance"
- Sender domain is a known payment/ERP system: `beis-chi-mail`, `nsknox`, `paymentadvice`
- Subject contains "FYI:" AND body references "payment number", "vendor number", "amount paid"

---

**D. Government**

Move here if ANY of:
- Sender domain ends in `.gov`, `.ae` and is a known government or authority body
- Sender is: `pcfc.ae`, `pcfc.voice`, `uhy-ae.com` (e-invoicing regulator)
- Subject contains: "circular", "regulatory", "compliance", "e-invoicing", "VAT", "trade licence"
- Email is from a free zone authority, municipality, ministry, or chamber of commerce
- Subject references "vendor registration" and sender is from a government-linked body (ADNOC, SNOC, McDermott vendor system for compliance, Al Ain Farms vendor update — these are client vendor portals, classify as Operational instead)

> **Tip:** PCFC (pcfc.ae, pcfc.voice@pcfc.ae) = Government. McDermott/BrandSafway vendor portals = Operational.

---

**E. Job Applications**

Move here if ANY of:
- Subject contains: "application", "CV", "resume", "vacancy", "career", "job opportunity", "applying for", "looking for job", "seeking employment", "job opening"
- Body opens with phrases like "I am applying", "I would like to apply", "please find my CV", "please find my resume", "I am looking for a position"
- Sender is a manpower recruitment agency (keywords: "recruitment", "manpower", "staffing", "placement", "talent", "HR services")

---

**F. Suppliers**

Move here if ALL of:
- Email is clearly from a vendor/supplier introducing themselves or their products
- The product/service is relevant to the shop: cutting tools, CNC machines, raw materials (steel, SS, alloy bar, pipe), calibration services, EDM wire, grinding wheels, inserts, tool holders, lubricants for machinery, honed tubes, chrome rods

Move here if ANY of:
- Sender is a known cutting tool brand/distributor: Guehring, EMUGE-FRANKEN, TruCut, ToolTech, Sandvik, Kennametal, Iscar, Ceratizit, Seco, Mitsubishi, Kyocera, Korloy
- Subject contains "tool catalogue", "cutting tool", "insert", "tool holder", "end mill", "drill", "tap", "EDM wire" AND sender is a supplier
- Sender is a steel/metal supplier and email is an introduction or offer (not an RFQ to Al Safeenah)
- Subject/summary references: "company profile", "product range", "we are manufacturer", "we supply", "we export" AND products are metal/engineering-related

Do NOT move to Suppliers:
- Emails from curtains, insulation, adhesive/glue, furniture, software, website, SEO, advertising companies → move to Spam
- Emails that are RFQs sent TO Al Safeenah from a supplier trying to get a quote → Business Critical

---

**G. Operational**

Move here if ANY of:
- Sender domain: `zoho.com`, `zohocorp.com`, `zohocrm.com`, `zohostore.com`, `zohoaccounts.com`, `zohocliq.com`, `yellowpages-uae.net`, `microsoft.com`, `accountprotection.microsoft.com`
- Subject contains: "new sign-in", "login activity", "password changed", "MFA", "multi-factor", "subscription", "onboarding", "YellowPages", "WhatsApp chat request"
- Email is from a logistics/freight company (TLS Logistics, Basenton, Winsail) sending shipment updates
- Email is an internal forward or test email from `@alsafeenah.ae`
- Email is from a monthly SEO report service (e.g., ATN, subject "Monthly SEO Report")
- Vendor portal gate pass approvals and access notifications (non-payment, non-order)

---

**H. Business Critical** ← default for genuine client/project emails

Move here if ANY of:
- Subject contains RFQ keywords: "RFQ", "request for quotation", "enquiry", "inquiry", "request for quote", "RFP", "tender", "quotation required", "please quote", "kindly quote", "submit your offer"
- Subject/summary mentions machining, fabrication, or Al Safeenah product keywords (see list below)
- Email is a reply thread from a known client (construction, oil & gas, marine, industrial) about an ongoing job
- Email is a follow-up or reminder about a previously submitted quotation
- Email is a purchase order, delivery note, quality rejection, or MTC/PMI request related to an active job
- Email is a PO acknowledgement from a client ERP system (e.g. McDermott's BEIS system, BrandSafway, SNOC, ABCO) — including automated "FYI: Standard PO" notifications referencing Al Safeenah as supplier
- Email is about material approval, drawing submission, or site access related to a project
- Subject contains: "PO", "purchase order", "delivery note", "invoice", "DO", "BFTR", "re:", "fw:" AND the thread is about an active job or order

**Business Critical machining/product keywords:** gear, roller, shaft, flange, bushing, bush, bearing, coupling, pipe spool, fabrication, machining, CNC, lathe, milling, turning, welding, fitting, rebar coupler, windsock, bollard, lifting cap, induction heating frame, cradle wheel, bronze bush, nylon roller, pressure die, pinion gear, worm gear, sprocket, piston, cylinder, valve, skid, tank, hydraulic block, bracing leg, rebar coupler, mechanical coupler, grooved wheel

---

### STEP 4 — Move Emails

For each email that has been classified (not SKIP), call:

```tool
ZohoMail_moveMessages
  accountId: <accountId>
  messageId: <messageId>
  currentFolderId: 2108081000000008014   ← always the Inbox
  destinationFolderId: <folder ID from table above>
```

**Batch where possible:** Group messages by destination folder and move up to 10 at a time if the API supports it.
If move fails for any individual email, log the failure and continue — do not abort the whole run.

---

### STEP 5 — Report to User

After all moves are complete, present a clean summary in chat:

```
📬 EMAIL SORT COMPLETE
──────────────────────────────────
Emails scanned    : <N>
Emails moved      : <N>
Left in inbox     : <N>

📂 Business Critical   → <N> emails
📂 Suppliers           → <N> emails
📂 Job Applications    → <N> emails
📂 Payment Remittance  → <N> emails
📂 Government          → <N> emails
📂 Operational         → <N> emails
📂 Spam                → <N> emails

Business Critical highlights:
  🟢 <subject> — from <sender>
  🟢 <subject> — from <sender>
  ...

Emails left in inbox (not sorted):
  • <subject> — <reason: unclear / irrelevant spam>
──────────────────────────────────
```

Highlight the top 3–5 Business Critical emails in the summary so the user knows what to action first.
If there are 0 emails in a category, omit that row from the report.

---

## Error Handling

| Situation | Action |
|---|---|
| Move API call fails | Log the email subject + error, skip it, continue |
| Folder ID not found | Call `ZohoMail_getAllFolders` and match by folder name to get fresh ID |
| Email already in target folder | Skip silently |
| Classification is ambiguous | Default to Business Critical (better to over-notify than miss) |
| Inbox is empty | Report "Inbox is already empty — nothing to sort" |
| More than 100 unread emails | Process the 100 most recent; note in summary that older emails may remain |

---

## Notes

- Run daily, ideally at the start of the working day, before checking the RFQ analyzer.
- The sorter does NOT delete any emails — only moves them between folders.
- Irrelevant spam (Chinese product promotions, insulation, curtains, adhesives, tenders platform spam,
  business loans, insurance cold outreach, generic SEO pitches) is moved to the Spam folder (ID: 2108081000000008024).
- When in doubt between Spam and a real category, always err toward the real category — it is better
  to over-file into Business Critical than to accidentally spam a genuine client email.
- This skill complements `rfq-email-analyzer`: run the sorter first, then run the RFQ analyzer on the
  Business Critical folder for a deeper dive on actionable quotation requests.
