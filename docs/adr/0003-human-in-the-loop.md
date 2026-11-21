# 0003 Human-in-the-loop, no credit scoring

**Status:** accepted

## Context
Creditworthiness assessment of natural persons is a high-risk use case under the EU AI Act (Annex III), and GDPR Art. 22 restricts decisions based solely on automated processing. Many SME borrowers (sole traders, partnerships) are natural persons.

## Decision
The app prepares; the advisor decides. There is no approve/decline prediction, no credit score and no single "fit score". Lenders are listed with hard-criteria checks, precedent counts ("approved 6 of 8 similar cases") and cited passages. Memos present facts and options, never a recommendation. Every memo needs explicit advisor approval, and a banner flags cases that concern a natural person.

## Consequences
- The system stays a decision-support tool and the reasoning is inspectable.
- Ranking lenders still needs an order: failing a hard check sorts last, then approval ratio among similar cases, but the raw counts are always shown.
