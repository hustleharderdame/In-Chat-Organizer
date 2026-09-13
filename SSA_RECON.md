---
node_id: "ssa_recon_master"
node_type: "system_spec"
version: "4.0.0"
status: "active"
single_source: true
tags:
  - "domain:financial-administration"
  - "status:active"
  - "tech:in-chat-pipeline"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Master_OS_Hub]]"
  - "[[BFR_v3.0.0]]"
  - "[[SSA_6233_BK_Field_Map]]"
  - "[[Canonical_Transaction_Model]]"
  - "[[Exception_Queue]]"
  - "[[Annual_Records_Checklist]]"
  - "[[Accountant_Notes]]"
---

# [[SSA_RECON]] — In-Chat Runtime

owner:: [[Damien_Brock]]
supersedes:: HLBIDX.00.SSA_RECON.MASTER_NODE.v3.3.0
case_id:: CASE-2026-001

**v4.0.0 changelog:** reconciled against [[BFR_v3.0.0]] (Universal
Beneficiary Financial Reconciliation & Audit Builder) — this node is now
the Case Layer instance running on the BFR architecture. Tag syntax
converted from hash-namespace to BFR's colon-namespace (single canon,
old tags in Section 16 are historical translation only). Added Hermes
build-order recommendation.

> [!note] Sub-node resolution
> `[[Canonical_Transaction_Model]]`, `[[SSA_6233_BK_Field_Map]]`,
> `[[Exception_Queue]]`, `[[Annual_Records_Checklist]]` and
> `[[Accountant_Notes]]` are defined **in this node**, at Sections 3, 4/9,
> 5, 13 and 15 respectively — this node is `single_source: true` for all
> of them. Reference them by section (the same way
> [[Chat_Root_Organizer_Service]] Section 2 is cited as the DDL SSOT);
> do not restate them elsewhere.
> `[[BFR_v3.0.0]]` is an **external node — not in this repo.**

## 0. Why v3.0.0 differs from v2.0.0

v2.0.0 was written for a background multi-agent runtime (7 autonomous agents,
persistent file tree, scheduled reconciliation). Chat has none of that —
no process runs between turns, nothing persists unless I explicitly write it.

v3.0.0 keeps every principle from v2.0.0 (reconcile-don't-rewrite, immutable
source data, uncertainty preserved as `UNKNOWN` not guessed) and collapses
the 7 agents into 5 phases I execute directly, live, using code execution
for the arithmetic. The SSA form fields are no longer placeholders — they're
pulled from the actual current SSA-6233-BK.

## 1. Governing axiom (unchanged from v2.0.0)

**The objective is not to make the records look good. The objective is to
make the financial reality understandable, supportable, correctable, and
defensible.** Nothing hidden, nothing invented, everything reconciled.

## 2. Pipeline (5 phases, run in-chat)

```
RAW STATEMENTS/RECEIPTS
        │
        ▼
PHASE 1 — INGEST        upload CSVs/PDFs/screenshots → parsed into
                         [[Canonical_Transaction_Model]] rows. No
                         classification yet. Nothing overwritten.
        │
        ▼
PHASE 2 — CLASSIFY       each txn → category + confidence. Anything
                         under 0.65 confidence stays UNKNOWN, goes to
                         [[Exception_Queue]]. No keyword-guessing
                         ("Walmart" ≠ groceries without evidence).
        │
        ▼
PHASE 3 — RECONCILE      code execution does the math: beginning
                         balance + deposits − withdrawals = expected
                         ending balance, checked against actual bank
                         ending balance. Regular funds and dedicated
                         account reconciled separately — never netted
                         against each other.
        │
        ▼
PHASE 4 — RESOLVE        you clear the Exception Queue (the only phase
                         that needs your factual knowledge — receipts,
                         explanations, "that ATM withdrawal was rent
                         cash for X").
        │
        ▼
PHASE 5 — MAP TO SSA-6233-BK   reconciled totals dropped into the
                         actual form fields (below). Nothing goes in
                         a field I can't trace back to a source
                         transaction.
```

## 3. [[Canonical_Transaction_Model]]

Immutable fields (never overwritten — corrections are new events, logged):
`date`, `description_raw`, `amount`, `account_id`, `source_document`.

Mutable fields (versioned):
`category`, `beneficiary_purpose`, `confidence`, `compliance_status`,
`evidence_refs[]`.

```json
{
  "txn_id": "TXN-0184",
  "date": "2026-08-14",
  "description_raw": "WALMART #2384",
  "amount": 83.42,
  "account_id": "ACCT-DED",
  "account_type": "dedicated",
  "category": "UNKNOWN",
  "confidence": 0.41,
  "compliance_status": "UNDETERMINED",
  "evidence_refs": []
}
```

`UNKNOWN ≠ misuse. UNKNOWN ≠ valid. My confidence score ≠ an SSA determination.`

## 4. [[SSA_6233_BK_Field_Map]] — verified against the live form

**A. Regular accountable funds** (food/housing/clothing/medical-dental not
covered elsewhere/education/recreation/personal items — reported as
lump categories, not line items):

| Form question | What it asks | Reconciliation source |
|---|---|---|
| Did payee decide how funds were used? | Y/N | fixed answer |
| Amount spent — food and housing | $ total | sum of category=HOUSING + FOOD |
| Amount spent — other (clothing, education, medical/dental, recreation, personal) | $ total | sum of category=CLOTHING/EDUCATION/MEDICAL/RECREATION/PERSONAL |
| Amount saved | $ balance as of last month of report period | ending balance, regular account |
| Institution beneficiary, <$360/yr personal needs | explanation required | flag if applicable |

**B. Dedicated account** (only if one exists):

| Form question | What it asks | Reconciliation source |
|---|---|---|
| Money taken out during period? | Y/N | any DR txn on ACCT-DED |
| Was each purchase impairment-related? (medical treatment, education, job skills training, therapy, or other impairment-benefit) | Y/N per item, explain if N | category=MEDICAL/THERAPY/EDUCATION/SENSORY → Y; anything else → N + must explain |
| Ending balance, incl. interest | $ | dedicated account reconciliation |

Everything in this table is required to be **impairment-related** for the
dedicated account — that's a materially different (narrower) test than
"reasonable expense." The Exception Queue should flag anything on
ACCT-DED that doesn't clearly meet it, *before* it becomes a form answer.

## 5. [[Exception_Queue]] format (in-chat)

```
🔴 TXN-184  Walmart  $83.42  — no category evidence. Dedicated account.
🟡 TXN-193  ATM  $300.00  — cash, purpose undocumented
🟢 TXN-201  Medical provider  $250.00  — receipt confirmed, impairment-related
```

Only 🔴/🟡 need your input. 🟢 is resolved automatically once evidence links.

## 6. What I need to start Phase 1

- Report period start/end dates (the form has a fixed accounting window)
- Bank statements/CSVs for the regular account, and the dedicated account if one exists
- Receipts or documentation for anything you already have on hand
- Beneficiary's relationship to you, and whether they're a minor or adult beneficiary (changes some form questions)

## 7. Boundaries (unchanged from v2.0.0)

Not a legal or SSA determination engine. I calculate, classify, and flag —
you resolve factual exceptions and approve what goes on the form before
it's submitted.

## 8. How to use this, turn by turn

1. **Start a period** — send report period dates + statements. I run Phase 1–2 and reply with a ledger summary + Exception Queue.
2. **Work the queue** — you answer 🔴/🟡 items in plain language ("TXN-193 was rent cash for the beneficiary's apartment"). I log it as a new event, never overwrite the original row.
3. **Check status anytime** — say `show ledger`, `show queue`, or `show totals` (formats in Section 12). No fixed order — ask whenever.
4. **Add late statements** — drop them in any time; I re-run Phase 3 reconciliation, don't restart from scratch.
5. **Map to the form** — say `map to 6233` once the queue is clear (or you accept the open items as-is). I output the field-by-field answers from Section 9, sourced to totals you can trace back to transactions.
6. **You sign it** — I never submit anything. You review the mapped values against the actual mailed form and file it yourself.

## 9. [[SSA_6233_BK_Field_Map]] — direct crosswalk to form line text

**Regular accountable funds:**

| Form line (verbatim) | System source |
|---|---|
| "Did you (the payee) decide how the total accountable amount was used?" | fixed Y/N you confirm |
| "How much of the total accountable amount did you spend for the beneficiary's food and housing?" | Σ category = HOUSING + FOOD |
| "How much of the total accountable amount did you spend on other things for the beneficiary such as clothing, education, medical and dental expenses, recreation, or personal items?" | Σ category = CLOTHING + EDUCATION + MEDICAL + RECREATION + PERSONAL |
| "How much, if any, of the total accountable amount did you save for the beneficiary as of the last month in the report period?" | regular account ending balance |
| Institution beneficiary, <$360/yr personal needs — explain | auto-flagged if applicable, you supply the explanation |

**Dedicated account (only if one exists):**

| Form line (verbatim) | System source |
|---|---|
| "Did you take money out of the dedicated account?" | any debit on ACCT-DED during period → Yes |
| "Is the purchase related to the impairment?" (medical treatment, education, job skills training, or other impairment-benefiting purchase) | category = MEDICAL/THERAPY/EDUCATION/SENSORY → Yes; anything else → No, with your explanation required |
| Dedicated account ending balance, including interest | dedicated account reconciliation |

## 10. Do / Don't

**Do:**

- Log every transaction, even ones you're sure about — the audit trail only works if nothing skips the pipeline
- Let uncertain items sit as `UNKNOWN` until real evidence resolves them
- Keep the regular account and dedicated account reconciled separately, always
- Re-run reconciliation whenever a late statement shows up
- Keep receipts/statements yourself for 2 years — SSA wants them retained, not submitted

**Don't:**

- Don't pick a category just to clear a 🔴 — an unresolved exception is safer than a wrong one on a form you sign under penalty of perjury
- Don't net a personal-funds beneficiary expense against a dedicated-account shortfall — they're two separate accounting facts (Section 11 of v2.0.0)
- Don't call something "impairment-related" on the dedicated account without a documented reason — that's a narrower test than "reasonable expense"
- Don't edit `description_raw`, `amount`, or `date` on a logged transaction — corrections are new events, not overwrites
- Don't mail supporting documents with the form unless SSA specifically requests them

## 11. Checklist (work through in order)

- [ ] Report period start/end confirmed
- [ ] All regular-account statements for the period uploaded
- [ ] Dedicated-account statements uploaded (if one exists)
- [ ] Receipts/evidence you already have attached to their transactions
- [ ] Every 🔴 in the Exception Queue resolved or knowingly accepted as unresolved
- [ ] Regular account: expected ending balance matches actual bank balance (or variance explained)
- [ ] Dedicated account: same check, separately
- [ ] `map to 6233` output reviewed line-by-line against your actual mailed form
- [ ] Source ledger + evidence saved somewhere you control (not just this chat) for the 2-year retention window

## 12. In-chat viewer commands ("what I put in there")

`show ledger` →

```
LEDGER — Aug 2026 (184 txns)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCT-REG   Housing  $612  |  Food  $340  |  Other  $118
ACCT-DED   Medical  $250  |  Therapy $180 | Unresolved $83.42
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`show queue` →

```
🔴 TXN-184  Walmart          $83.42   ACCT-DED — no evidence
🟡 TXN-193  ATM               $300.00  ACCT-REG — cash, undocumented
🟢 TXN-201  Medical provider  $250.00  ACCT-DED — receipt confirmed
```

`show totals` →

```
REGULAR:    Beginning $1,240 + Deposits $914 − Spent $1,070 = Expected $1,084
            Actual bank balance: $1,084  ✅ MATCH

DEDICATED:  Beginning $2,000 + Deposits $0 − Spent $430 = Expected $1,570
            Actual bank balance: $1,570  ✅ MATCH
```

`map to 6233` → the Section 9 table filled with your period's actual numbers.

## 13. [[Annual_Records_Checklist]] — full report-period year

SSA's accounting window is typically 12 months. Gather these before Phase 1:

- [ ] 12 monthly statements — regular/representative-payee account
- [ ] 12 monthly statements — dedicated account (if applicable)
- [ ] SSA award/benefit letters for the period (confirms amounts SSA says it paid — used to check deposits)
- [ ] Any prior-period SSA-6233-BK confirmation of carried-forward savings balance
- [ ] Receipts for medical, therapy, education, or job-skills purchases from the dedicated account (these need documentation, not just the bank line)
- [ ] Receipts or explanation for any ATM/cash withdrawals over the period
- [ ] Documentation for any large or one-off purchases (>$100 is a reasonable internal flag threshold)
- [ ] Records of interest earned on the dedicated account, if any

## 14. Online vs. in-person submission

SSA gives three real paths for SSA-6233-BK — pick based on what's actually going on with the account, not convenience alone:

| Path | How it works | Best when |
|---|---|---|
| **Online (iRPA)** — ssa.gov/payee/form | Needs the unique code printed on the paper form SSA mailed you. Must be completed in **one sitting** — no saving partial progress, no attachments. You get a confirmation number at the end. | The numbers are clean, reconciled, and you're just reporting totals — no exceptions left to explain in your own words. |
| **Phone, then mailed back for signature** | SSA rep takes your answers by phone, mails you the completed form to sign and return. | Similar to online — clean numbers, but you'd rather talk it through than type it. |
| **In person / face-to-face interview** | You bring records, an SSA rep asks the questions live and helps complete the form. | **This is the stronger path if the Exception Queue has unresolved or judgment-call items** — anything where "impairment-related" is arguable, where a variance needs explaining, or where the account has any history that could draw scrutiny. A human conversation lets you contextualize before the number ever gets typed in, and gives you a named contact if SSA follows up. |

Given what this system exists to handle — records that "may appear
confusing, incomplete, or alarming" until reconciled — **in-person is the
safer default** here unless a period comes back fully clean (every 🔴
resolved, both accounts reconciling to the penny, nothing on the dedicated
account outside the impairment-related categories). Online is for
routine, uneventful periods; it doesn't leave room to explain anything.

## 15. [[Accountant_Notes]] — meeting notes template

*No reconciliation has run yet, so this is the structure, not filled
numbers. Once Phase 1–4 are done, `map to accountant notes` will drop
your actual figures into this template.*

```
ACCOUNTANT PREP — SSA REP PAYEE ACCOUNTING
Period: [start] – [end]
Beneficiary: [name/relationship]

1. HEADLINE NUMBERS
   Regular account:   Beginning $___ → Ending $___  [MATCH / VARIANCE $___]
   Dedicated account: Beginning $___ → Ending $___  [MATCH / VARIANCE $___]

2. WHAT I NEED THEM TO LOOK AT
   - Any MATERIAL_VARIANCE line (unexplained by transaction evidence)
   - Any transaction still UNKNOWN after I've tried to resolve it
   - Any dedicated-account purchase where "impairment-related" is a
     judgment call, not a clear Yes
   - Household-allocation math, if shared expenses were split with the
     beneficiary's funds (accountant should confirm the methodology
     before it goes on the form, not after)

3. QUESTIONS FOR THE ACCOUNTANT
   - Does this variance need a formal correcting entry, or just a
     documented explanation?
   - Is there a cleaner way to categorize [specific transaction type]
     for SSA's purposes vs. how I have it internally?
   - Given the exceptions still open, should this period go in person
     or is [item] minor enough for online/phone?

4. WHAT I'M BRINGING
   - Full reconciled ledger (not just the form totals)
   - Evidence index — receipts/documentation tied to each flagged item
   - Prior period's SSA-6233-BK, if this isn't the first report
```

## 16. Tagging taxonomy *(historical — superseded by Section 20)*

Every node and every transaction carries hierarchical tags — this is what
makes `show queue` / `show ledger` filterable instead of a wall of text.

```
#domain/financial-administration      (fixed, root)
#account/regular                      #account/dedicated
#category/housing  #category/food  #category/clothing
#category/medical  #category/therapy  #category/education
#category/sensory  #category/recreation  #category/personal
#category/transfer  #category/atm-cash  #category/unknown
#compliance/validated  #compliance/potentially-valid
#compliance/undetermined  #compliance/potential-misapplication
#compliance/confirmed-misapplication
#status/open  #status/resolved  #status/needs-evidence
#phase/ingest  #phase/classify  #phase/reconcile  #phase/resolve  #phase/mapped
#evidence/receipt  #evidence/bank-statement  #evidence/provider-doc
#evidence/missing
#impairment/related  #impairment/unrelated  #impairment/undetermined
```

Rule: a transaction is never tagged `#compliance/validated` without at
least one `#evidence/*` tag other than `#evidence/missing`. That's the
enforcement mechanism — the tag set itself won't let a claim outrun its
proof.

## 17. Linking structure (node graph)

```
[[SSA_RECON]]  (this node — root)
     ├── [[Canonical_Transaction_Model]]
     │        └── each TXN-#### links → [[Evidence:<doc_id>]]
     │                                → [[Exception_Queue]] (if open)
     │                                → [[SSA_6233_BK_Field_Map]] (once mapped)
     ├── [[Exception_Queue]]
     │        └── each entry links → source TXN-####
     │                             → [[Accountant_Notes:<period>]] (if escalated)
     ├── [[SSA_6233_BK_Field_Map]]
     │        └── each field links → the category tags it sums
     ├── [[Annual_Records_Checklist]]
     └── [[Accountant_Notes:<period>]]
              └── links back → every TXN-#### it references
```

Backlink rule: nothing gets created as an orphan. A transaction with no
link to evidence, and no link to an exception, is itself a data-integrity
flag — `show orphans` surfaces anything not connected to the graph.

Per-period nodes get their own id so history stays intact:
`[[SSA_RECON_2026_AUG]]`, `[[Accountant_Notes_2026_AUG]]` — each links up
to `[[SSA_RECON]]` as parent and sideways to the transactions it covers.

## 18. Dynamic markup library

Inline fields (Dataview-style key:: value), for anything you paste into
Obsidian alongside the chat output:

```
account:: [[ACCT-DED]]
period:: [[2026-08]]
compliance:: undetermined
impairment:: unrelated
reviewed-by:: [[Damien_Brock]]
```

Live query blocks — drop these in your vault, they stay current as new
transactions get logged:

```dataview
TABLE amount, category, compliance AS "Status"
FROM #domain/financial-administration
WHERE contains(tags, "status/open")
SORT amount DESC
```

```dataview
TABLE WITHOUT ID account_id, sum(amount) AS "Total"
FROM #account/dedicated
WHERE contains(tags, "impairment/unrelated")
GROUP BY account_id
```

Callouts for the three severity tiers, matching the 🔴🟡🟢 queue markers:

```
> [!danger] TXN-184 — Walmart $83.42
> No evidence linked. Dedicated account. Blocks form mapping until resolved.

> [!warning] TXN-193 — ATM $300.00
> Cash withdrawal, purpose undocumented. Needs your explanation.

> [!success] TXN-201 — Medical provider $250.00
> Receipt confirmed, impairment-related. Ready to map.
```

Embeds, for pulling the live ledger view straight into a period note
instead of re-typing it:

```
![[SSA_RECON_2026_AUG#Ledger Summary]]
```

## 19. Relationship to [[BFR_v3.0.0]]

BFR is the reusable, builder-agnostic platform spec. This node —
`SSA_RECON` — is one **Case** running on top of it:

```
case_id:: CASE-2026-001
program:: SSA
beneficiary_id:: BEN-001
payee_id:: [[Damien_Brock]]
```

The 5-phase in-chat pipeline (Section 2) maps directly onto BFR's agent
architecture (BFR Section 29):

| This node's phase | BFR agent |
|---|---|
| Ingest | Parser |
| Classify | Classifier + Evidence Agent |
| Reconcile | Accountant |
| Resolve | Review Agent (human-in-loop) |
| Map to 6233 | Report Agent |

Nothing here contradicts BFR — this is the operating layer I run with you
turn by turn; BFR is what Hermes eventually persists it into.

## 20. Tag syntax — canon conversion

BFR's colon-namespaced tags (BFR Section 04) are now canon, superseding the
hash-tags in Section 16 of this node. Translation for anything already logged:

| Old (v3.3.0) | New canon (BFR) |
|---|---|
| `#account/regular` `#account/dedicated` | `account:regular` `account:dedicated` |
| `#category/medical` etc. | `purpose:medical` etc. |
| `#compliance/validated` etc. | `compliance:validated` etc. |
| `#evidence/receipt` etc. | `evidence:receipt` etc. |
| `#impairment/related` | fold into `purpose:*` + `RULE-SSA-DED-*` link (BFR Sections 22-23) — impairment-relatedness is a rule evaluation, not a standalone tag |

The enforcement rule carries over unchanged: no `compliance:validated`
tag without a linked evidence object other than `evidence:none`.

## 21. Hermes build order (do not build all 20 BFR phases at once)

**Batch 1 — build now:** BFR Phases 1-8 (discover environment, discover
House of Brock, data model, tag engine, link engine, source ingestion,
canonical ledger, evidence system). This is enough to hold one real
reconciled period.

**Batch 2 — after Batch 1 is verified against a real period:** Phases
9-14 (rule engine, reconciliation, exceptions, corrective action,
controls, SSA mapping).

**Batch 3 — only once Batch 1-2 are trusted:** Phases 15-16, 42-43
(reporting UI, CLI, API). Don't build an interface for a data layer
that hasn't proven itself yet.

Test gate between every batch: BFR Sections 55/56 — don't claim completion
without verification, and reuse this chat's already-reconciled period
as the first test case rather than inventing synthetic data.
