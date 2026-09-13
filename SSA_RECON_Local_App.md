---
node_id: "ssa_recon_local_app"
node_type: "tool"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain:financial-administration"
  - "status:active"
  - "tech:standalone-html"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Master_OS_Hub]]"
  - "[[SSA_RECON]]"
  - "[[SSA_RECON_App_UI]]"
---

# [[SSA_RECON_Local_App]] — offline reconciliation tool

owner:: [[Damien_Brock]]
file:: `standalone/ssa-recon.html`
runs:: open the file in any browser · no server, no install, no account
selftest:: `standalone/ssa-recon.html?selftest` · 48 checks
demo:: `standalone/ssa-recon.html?example`

One HTML file implementing Phases 1–5 of [[SSA_RECON]] on a single device.
Nothing leaves the machine. Authority for every rule it applies remains
[[SSA_RECON]], cited by section.

## 1. Where the language model sits, and why it sits there

The optional model **never computes, categorises, or decides.** It proposes a
label for a merchant description no rule matched; the proposal appears in the
queue and is worth nothing until a person accepts it, at which point the event
log records it as the payee's decision.

This is not caution for its own sake. A 0.5B model asked to add
`1,240.00 + 11,388.00 − 11,543.58` will sometimes be wrong, and Section 1's
axiom is that the result must be defensible. So the split is absolute:

| Deterministic JavaScript | The model |
|---|---|
| All arithmetic, in integer cents | Suggests a label for one unmatched string |
| Reconciliation and variance | — |
| Category rules | — |
| Queue construction and gating | — |
| Form mapping | — |

Every screen works with no model present. It is a convenience, never a
dependency, and the download is opt-in.

## 2. Money is integer cents

Floating point cannot hold a ledger — `0.1 + 0.2` is not `0.3`. Amounts parse
to whole cents at the edge, stay integers through every sum, and format back
only for display. Two self-tests pin this.

## 3. What it enforces from [[SSA_RECON]]

- **Accounts never net** (Section 10) — separate objects, separate proofs
- **No guessed categories** (Section 2) — a rule hit is confidence 1, anything
  else is `UNKNOWN` at 0; there is no persuasive middle value
- **Unresolved money is never bucketed** — `UNKNOWN` and `ATM_CASH` spending is
  excluded from both reported figures and reported separately, so the two
  buckets always account for every penny that left the account
- **Dedicated spending needs evidence and an impairment answer** (Sections 4B,
  9, 16) before it can clear
- **The form is gated** (Section 2) — a blocked answer prints `——` and names
  the exception holding it up
- **Corrections are events** (Section 3) — the log appends, the row is not rewritten

## 4. Persistence

Closes the gap named in [[SSA_RECON]] Section 0: nothing survives a session on
its own. Two exports —

- **State (`.json`)** — reload later and carry on
- **Period node (`.md`)** — Section 17's `[[SSA_RECON_YYYY_MON]]`, front-matter
  and wikilinks intact, to commit into this graph

## 5. Limits

- [ ] The model path is **untested** — no weights were downloaded during the build
- [ ] Model weights load from a CDN, so first use needs network; a published
      Artifact cannot do this at all (`connect-src 'self'`), which is why this
      is a local file
- [ ] CPU inference is slow; the model is there for a handful of stubborn rows
- [ ] Form wording inherits the unverified-text risk in Section 9
- [ ] CSV import expects a signed amount column or a debit/credit pair
- [ ] Evidence is a checkbox and a note, not stored documents
