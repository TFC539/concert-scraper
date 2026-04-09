# Concert Data Platform – Developer Overview (Updated)

## 1. Goal

Build a reliable, scalable system that converts unstructured concert data into a structured, validated database of:

- events
- performers
- works
- venues

The system combines:
- AI extraction (LLM)
- deterministic matching
- human validation (initially solo, later community-assisted)

Primary objective:
→ **high-quality, trustworthy data over maximum automation**

---

## 2. Core Principles

- LLM is NOT the source of truth (only extraction + assistance)
- Database integrity > automation (avoid false merges at all cost)
- Prefer missing data over incorrect data
- No direct edits to canonical data
- All changes go through proposal + review
- System improves via feedback (aliases, decisions, exclusions)

---

## 3. High-Level Architecture


Scraper → LLM Extraction → Normalization → Matching → Triage → Proposal Layer → Review → Canonical DB


---

## 4. Responsibilities by Layer

### 4.1 Scraper
- Collect concert data (initial scope: Hamburg + Northern Germany)
- Clean HTML → plain text
- Provide structured input to LLM

---

### 4.2 LLM (OpenRouter – Gemini Flash Lite)

Used ONLY for:
- extracting structured data (performers, works, venue, date)
- optional disambiguation (small candidate sets only)

NOT used for:
- matching decisions
- merging entities
- tagging core data

---

### 4.3 Normalization Layer

- transliteration (e.g. Hangul → Latin)
- string normalization (case, spacing, punctuation)
- name order handling
- work parsing (composer, opus, key, etc.)
- venue standardization

---

### 4.4 Matching Layer

- exact alias match (primary)
- normalized match
- fuzzy / similarity scoring
- optional LLM disambiguation (only when ambiguous)

---

## 5. Triage System (Critical for Solo Phase)

All extracted entities are split into 3 buckets:

### 🟢 Safe (auto-accept)
- exact alias matches
- known venues
- high confidence matches (>0.95)

→ automatically written to canonical DB

---

### 🟡 Medium confidence (review later)
- strong fuzzy matches
- recurring performers

→ stored but not blocking

---

### 🔴 Critical (manual review)
- new performers
- ambiguous matches
- low confidence (<0.85)

→ ONLY these require immediate review

---

## 6. Proposal Layer

All non-safe operations become proposals (no direct DB writes).

Types:
- match proposal (input → existing entity)
- new entity proposal
- correction proposal
- merge suggestion (restricted)

---

## 7. Review Workflow


Proposal → Review → Decision → Apply → Learn


Initially:
→ only you review

Later:
→ community-assisted

---

## 8. Canonical Database

Stores ONLY validated data:

- performers
- works
- venues
- events (linked to entities)

This is the single source of truth.

---

## 9. Feedback & Learning

Each decision updates:

- alias tables (name variations)
- matching confidence
- exclusion rules (do_not_merge)

System becomes more accurate over time.

---

## 10. Community System (Planned)

### 10.1 User Capabilities

Users can:
- report incorrect data
- suggest corrections
- confirm/reject proposals

Users CANNOT:
- directly edit database
- auto-merge entities

---

### 10.2 Trust Levels

- new users → low influence
- trusted users → higher weight
- verified users → strong influence

---

### 10.3 Consensus Logic

- AI provides initial confidence
- users vote (weighted)
- decision applied only after threshold reached

---

### 10.4 Safety

- merges require stricter thresholds
- “do not merge” flags prevent repeated mistakes
- full audit log for all changes

---

## 11. Frontend Requirements (VERY IMPORTANT)

### 11.1 Public UI

- display concerts cleanly
- handle missing data gracefully
- allow issue reporting:
  → “Report incorrect data” button

---

### 11.2 Contributor UI (Internal → later public)

This is intentionally “annoying” but functional.

Must include:

#### Authentication
- user accounts
- login / signup
- basic session handling

---

#### Triage Dashboard

Sorted by:
- lowest confidence first
- unresolved first

Each item shows:
- input value
- candidate matches
- confidence score

Actions:
- accept match
- create new entity
- reject
- skip

---

#### Proposal Review UI

For each proposal:
- show suggestion
- show AI confidence
- show source
- allow:
  - approve
  - reject
  - suggest alternative

---

#### Batch Handling

Must support:
- resolving repeated entities once (apply to all)
- grouping similar entries

---

## 12. Tagging System (Separate Layer)

- NOT part of extraction
- NOT part of core data

Handled as enrichment:

- rule-based when possible
- LLM fallback when ambiguous
- stored with confidence

---

## 13. Web Search (Optional)

Used ONLY for:
- enrichment
- rare disambiguation

NOT used for:
- extraction
- matching

---

## 14. Backfill Strategy

- process new data first
- stabilize system
- reprocess old data in batches
- compare before overwriting

---

## 15. Deployment Scope

### Phase 1
- Hamburg + nearby
- limited venues
- high accuracy focus

### Phase 2
- Northern Germany

### Phase 3
- expansion

---

## 16. Key Risks

- incorrect merges (highest priority)
- over-reliance on LLM
- uncontrolled user edits
- skipping triage → overload

---

## 17. Key Insight

This system is not just a scraper.

It is:
→ **a validated, self-improving concert data system**

---

## 18. Summary

- AI extracts data
- system matches deterministically
- only uncertain cases are reviewed
- users contribute signals, not direct edits
- database remains clean and trustworthy
- system improves continuously over time
Nope don’t write it as „hey we need this“ but „hey we need to change the current system to do this“
# Concert Data Platform – System Update Briefing

## 1. Objective

We need to evolve the current system from a **pure extraction pipeline** into a **validated, confidence-driven data system with controlled human input**.

The goal is to:
- improve data reliability
- reduce manual workload
- enable future community contributions
- prevent incorrect merges or corrupted data

---

## 2. Required Architectural Change

### Current (implicit)
```text
Scraper → Extraction → DB
Target
Scraper → LLM Extraction → Normalization → Matching → Triage → Proposal Layer → Review → Canonical DB

Key change:
→ Introduce separation between raw results and validated data

3. Introduce Triage System (Critical Change)

Instead of treating all extracted data equally, we must classify results into:

🟢 Safe (auto-accept)
exact alias matches
known venues
high-confidence matches (>0.95)

→ directly written to canonical DB

🟡 Medium confidence (deferred review)
strong fuzzy matches
recurring performers

→ stored, not blocking

🔴 Critical (manual review required)
new performers
ambiguous matches
low confidence (<0.85)

→ only these require immediate attention

Reason

We currently cannot manually review all entries.
This change reduces workload to only high-risk cases.

4. Introduce Proposal Layer (Required)

We must stop writing uncertain data directly to the main database.

All non-safe operations must be stored as proposals.

Types:

match proposal
new entity proposal
correction proposal
merge suggestion (restricted)

Key rule:
→ Canonical DB must only contain validated data

5. Matching Responsibility Adjustment

We need to explicitly separate responsibilities:

LLM
extraction only
optional disambiguation (small candidate sets)
System (code)
normalization
candidate retrieval
matching decisions
confidence scoring

→ LLM must NOT make database decisions

6. Feedback & Learning Layer

We must introduce persistent learning:

alias storage (name variations)
transliteration mappings
“do not merge” rules
confidence tuning

Every reviewed decision must improve future matching.

7. Frontend Requirements (New Requirement)

We need to introduce a minimal but functional contributor interface.

7.1 Authentication
user accounts required
login / signup
session handling
7.2 Triage Dashboard

Required for both internal use and future contributors.

Must include:

list of unresolved / low-confidence entries
sorted by priority (lowest confidence first)

Each entry must show:

extracted value
candidate matches
confidence score

Actions:

accept match
create new entity
reject
skip
7.3 Proposal Review Interface

For each proposal:

display suggestion
show AI confidence
show source

Actions:

approve
reject
suggest alternative
7.4 Batch Handling (Important)

System must support:

resolving repeated entities once (apply globally)
grouping similar entries
Note

UI can be minimal and “functional over polished”
→ priority is speed of validation, not UX perfection

8. Community Contribution Model (Future-Ready)

We need to design system to support:

user-submitted corrections
proposal voting
trust-based weighting

BUT:

→ users must NOT directly edit canonical data
→ all contributions go through proposal layer

9. Data Integrity Rules (Must Enforce)
never auto-merge unless near certainty
false merge is worse than duplicate
prefer missing data over incorrect data
maintain full audit trail of changes
10. Tagging System Adjustment

Tagging must NOT be part of extraction.

Instead:

move to separate enrichment layer
use rule-based tagging where possible
use LLM only when ambiguous
store tags with confidence
11. Web Search Usage

Web search must NOT be part of:

extraction
matching

Allowed only for:

enrichment
rare disambiguation
12. Backfill Strategy (Deferred Change)

We must:

stabilize pipeline on new data
then reprocess historical data in batches
compare before overwriting
13. Deployment Scope

Initial system remains limited to:

Hamburg + surrounding region

Reason:

faster learning
higher accuracy
manageable dataset
14. Expected Impact

After implementing these changes:

manual workload decreases significantly
system becomes self-improving
data quality increases over time
system becomes ready for public release
15. Summary

We are transitioning from:

→ automated extraction system

to:

→ validated, triaged, human-assisted data system

Key additions:

triage layer
proposal system
review workflow
contributor UI
learning mechanisms

Primary goal:
→ reliable, trustworthy concert data at scale