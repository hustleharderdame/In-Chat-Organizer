---
node_id: "ssa_recon_app_ui"
node_type: "design_spec"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain:financial-administration"
  - "status:active"
  - "tech:mobile-ui"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Master_OS_Hub]]"
  - "[[SSA_RECON]]"
  - "[[Exception_Queue]]"
  - "[[SSA_6233_BK_Field_Map]]"
---

# [[SSA_RECON_App_UI]] — mobile surface

owner:: [[Damien_Brock]]
surface:: mobile · 390×844
source:: `design/ssa-recon/*.dc.html` + `canvas.json`
canvas:: https://claude.ai/code/artifact/5add8b9d-b06f-4830-8fa2-9729a63c092f

`single_source: true` for the app's information architecture and visual
tokens. It is **not** authority for any rule it displays — every figure,
threshold and form field traces to [[SSA_RECON]], cited by section.

## 1. What this replaces

The prior concept was a six-step form wizard: onboarding → progress bar →
"Claimant Information" → submit. That inverts [[SSA_RECON]] Section 2, where
the form is Phase 5 of 5 and nothing may enter a field without a source
transaction behind it. Six specific defects, each fixed by a screen below:

| Defect in the wizard | Rule it broke | Fix |
|---|---|---|
| No ingest, classify or reconcile surface | Section 2, Phases 1–3 | Screens 2–3, and Home |
| No exception queue | Section 5 | Screen 5, promoted to a tab |
| One progress bar over two accounts | Section 10 — never netted | Home, two separate cards |
| "Claimant Information" as one party | Section 6 — payee ≠ beneficiary | Screen 1, two labelled parties |
| Progress measured form-fill, not truth | Section 12 — `show totals` | Home, MATCH / VARIANCE verdicts |
| No impairment-related test | Sections 4B, 9, 16 | Screen 6 |

## 2. Screen inventory

Artboard stems map to `design/ssa-recon/<stem>.dc.html`.

| # | Artboard | Phase | Carries |
|---|---|---|---|
| — | `Main` | status | Two account cards, phase rail, gated form CTA |
| 1 | `PeriodSetup` | 1 | Window dates, payee + beneficiary, adult/minor, accounts in scope |
| 2 | `Ingest` | 1 | Per-account statement coverage, evidence counts |
| 3 | `Ledger` | 2 | Account switcher, category split, confidence, UNKNOWN visible |
| 4 | `Queue` | 4 | Blocking / review / cleared triage |
| 5 | `Resolve` | 4 | Locked immutable fields, evidence, impairment test, event log |
| 6 | `FormMap` | 5 | Traced field answers, two blocked on named exceptions |
| 7 | `Submission` | — | Reasoned filing path (Section 14) |

**Navigation:** Period · Ledger · Queue · Form. The queue is a destination
with a count badge; Form sits locked behind it.

## 3. Load-bearing interaction rules

- **Two exception kinds must not look alike.** A transaction missing evidence
  (`TXN-184`) and an account that does not tie (`VAR-REG-01`) share the queue
  but are answered by different means — a receipt versus an explanation.
- **Immutable fields render locked.** `date`, `description_raw`, `amount`,
  `account_id`, `source_document` sit in a disabled block; answers append as
  new events (Section 3, Section 10).
- **A reconciled account can still be blocked.** Home deliberately shows the
  dedicated account balancing to the penny while one purchase remains
  unproven — balance truth and evidence truth are separate verdicts.
- **No field is filled without its source.** Mapped answers carry the sum and
  transaction count behind them; unfillable ones stay blank and name the
  exception holding them up.
- **Filing is a recommendation, not a button.** Online is shown unavailable
  with its real reason: one sitting, no attachments, nowhere to explain a
  variance (Section 14).

## 4. Tokens

Forest green is from the product concept; the danger, warning and neutral
values are lifted from `chat_organizer/web/app.html` so both front-ends in
this repo share a palette root.

```
brand      #1F3D33   brand-dark  #16302A   sage       #E7EFE8
ground     #F6F6F4   card        #FFFFFF   border     #DBD8D1
border-2   #ECEAE5   ink         #16201C   ink-2      #5A655F
ink-3      #8A938D   danger      #A33A2C   warning    #B57715
ok         #2E6B4F
```

`Source Serif 4` display · `IBM Plex Sans` UI · `IBM Plex Mono` for every
figure, transaction id and account code. Radii 8–14px. Controls ≥ 44px.

## 5. Constraints verified

- Every artboard measured headless at 390×844; all fit with 33–85px slack.
  Frames are `overflow: hidden`, so overflow clips silently — **re-measure
  after any content edit.**
- No painted status bar. The OS draws its own on top; a fake one doubles.

## 6. Open items

- [ ] Screens are static mockups — the queue → resolve loop is not clickable
- [ ] Form line text in [[SSA_6233_BK_Field_Map]] is unverified against the
      live SSA-6233-BK; the UI inherits that risk wherever it prints a field
- [ ] Figures shown are sample data from Section 12's worked examples; no real
      period has been reconciled
- [ ] Dedicated-account-absent variant not drawn (Section 4B is conditional)
- [ ] Empty, first-run and all-clear states not drawn

## 7. Rebuilding the canvas

Sources are the artboards and `canvas.json` under `design/ssa-recon/`. The
published canvas is generated from them and is gitignored — edit the sources
and re-seed, never the generated file.
