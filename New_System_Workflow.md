# Concert Data Extraction, Normalization, and Entity Resolution System

## 1. Overview

This system converts unstructured concert descriptions into a structured, normalized, and database-linked representation of events, performers, works, and venues.

The system is designed to:
- minimize cost (LLM used only where necessary)
- avoid incorrect merges (conservative matching)
- support multilingual and cross-script data (e.g. Hangul ↔ Latin)
- improve over time via feedback and alias expansion

The system separates responsibilities clearly:
- LLM: extraction and limited linguistic assistance
- Application logic: normalization, matching, and decision-making
- Database: source of truth

---

## 2. End-to-End Pipeline


Scraper → Raw Text → LLM Extraction → Normalization → Candidate Retrieval → Matching → Suggestion Engine → Resolution → Database


---

## 3. Input Layer (Scraper)

### Source
- Venue websites (HTML)
- Converted to cleaned plain text

### Example Input

Klavierabend mit 김선욱.
Werke von Chopin: Ballade Nr. 1 in g-Moll, op. 23
Elbphilharmonie Großer Saal


---

## 4. Extraction Layer (LLM)

### Objective
Extract structured data from raw text without performing any database matching.

### Output Schema (minimal, token-efficient)
```json
{
  "p": ["string"],           // performers
  "w": [
    {
      "c": "string",         // composer
      "t": "string"          // title
    }
  ],
  "v": "string",             // venue
  "d": "string (optional)"   // date
}
Example Output
{
  "p": ["김선욱"],
  "w": [
    {
      "c": "Chopin",
      "t": "Ballade Nr. 1 in g-Moll, op. 23"
    }
  ],
  "v": "Elbphilharmonie Großer Saal"
}
5. Normalization Layer

Transforms extracted values into canonical, comparable forms.

5.1 Performer Normalization

Steps:

detect script (Latin, Hangul, etc.)
transliterate to Latin if needed
normalize case, spacing, punctuation
generate variants (name order inversion)

Example:

Input:  김선욱
Output: ["gim seonuk", "kim sunwook", "sunwook kim"]
5.2 Work Normalization

Extract structured attributes from free-form titles:

Attributes:

composer (normalized)
form (e.g. sonata, ballade)
number
opus/catalogue number
key

Example:

Input:  Ballade Nr. 1 in g-Moll, op. 23
Output: {
  composer: "chopin",
  form: "ballade",
  number: 1,
  opus: 23,
  key: "g minor"
}
5.3 Venue Normalization
normalize punctuation and spacing
resolve known aliases to canonical name
6. Candidate Retrieval

For each normalized entity, retrieve a small set of candidates from the database.

Techniques:
ILIKE / trigram search (Postgres)
fuzzy matching
optional embedding similarity
Output Example
Input: "kim sunwook"

Candidates:
- Kim Sunwook (id: 123)
- Sunwook Kim (id: 456)

Candidate list should be limited (typically 3–10 entries).

7. Matching Layer

Matches normalized entities to database records.

7.1 Performer Matching

Process:

exact alias match → immediate accept
normalized match → high confidence
fuzzy / embedding match → scored candidate
optional LLM disambiguation (only if ambiguous)
Decision Rules
Condition	Action
exact / alias match	accept
score > 0.95	accept
0.85–0.95	LLM-assisted check
< 0.85	unresolved
LLM Disambiguation (optional)

Input:

Name: 김선욱
Candidates:
1. Kim Sunwook (id: 123)
2. Sunwook Kim (id: 456)

Output:

{
  "id": 123,
  "confidence": 0.94
}
7.2 Work Matching

Match using structured attributes:

composer
form
number
opus/catalogue
key
7.3 Venue Matching
deterministic alias lookup
typically no LLM required
8. Uncertainty Handling

If no match exceeds threshold:

{
  "status": "unresolved",
  "candidates": [
    { "id": 123, "score": 0.78 },
    { "id": 456, "score": 0.74 }
  ]
}

Unresolved entities are passed to the suggestion engine.

9. Suggestion Engine

Generates reviewable suggestions for ambiguous or conflicting cases.

9.1 Match Suggestions (incoming → DB)
{
  "type": "match_suggestion",
  "entity": "performer",
  "input": "Suyeon Kim",
  "candidates": [
    { "id": 123, "name": "Suyeon Kim", "score": 0.88 },
    { "id": 456, "name": "Sukyeon Kim", "score": 0.84 }
  ]
}
9.2 Merge Suggestions (DB ↔ DB)
{
  "type": "merge_suggestion",
  "entity": "performer",
  "candidate_a": { "id": 123, "name": "Suyeon Kim" },
  "candidate_b": { "id": 456, "name": "Sukyeon Kim" },
  "score": 0.72,
  "llm_assessment": "likely_different",
  "confidence": 0.25,
  "reason": "Names are similar but not typical transliteration variants"
}
Rules
never auto-merge based on suggestion
suggestions are advisory only
10. Resolution Layer

Human-in-the-loop interface for handling suggestions.

Actions
accept match
select alternative candidate
create new entity
merge entities
mark as distinct (do_not_merge)
Negative Link Example
do_not_merge(123, 456)

Prevents repeated incorrect suggestions.

11. Database Schema
performers
id | canonical_name | native_name
performer_aliases
performer_id | alias | script | normalized
works
id | composer | form | number | opus | key
venues
id | name | city
events
id | title | date | venue_id
event_performers
event_id | performer_id | role
event_works
event_id | work_id | sequence_order
12. Feedback Loop

System learns from all confirmed decisions:

On match:
add alias mapping
On merge:
unify entities
merge aliases
On rejection:
add exclusion rule (do_not_merge)
13. System Properties
conservative matching (avoid false merges)
deterministic where possible
LLM used only for:
extraction
optional disambiguation
cross-script support (Hangul, Latin, etc.)
incremental improvement over time
14. Example End-to-End Flow
Input
Recital with Kim Sunwook
Chopin Ballade No.1
Elbphilharmonie
Final Output
{
  "event": {
    "venue_id": 1
  },
  "performers": [
    {
      "performer_id": 123,
      "confidence": 0.99
    }
  ],
  "works": [
    {
      "work_id": 456,
      "confidence": 0.97
    }
  ]
}
15. Key Design Principles
LLM is not the source of truth
database integrity has priority over automation
false merges are worse than duplicates
matching is deterministic; LLM is assistive
system improves through feedback, not assumptions