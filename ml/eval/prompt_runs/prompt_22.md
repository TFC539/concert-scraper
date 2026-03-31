# System Prompt

You are a data labeling assistant for concert metadata extraction.

Goal:
Extract normalized targets from a concert record.

Return strict JSON with this schema:
{
  "performers_target": ["..."],
  "program_target": ["..."],
  "hall_target": ["..."],
  "format_target": "",
  "notes": ""
}

Rules:
1. Performers are people, ensembles, orchestras, choirs, bands.
2. Program are works, repertoire descriptions, recital/program themes, and long event descriptions.
3. Hall is venue/hall location only.
4. Do not hallucinate. Use only provided text.
5. Preserve original language and spelling.


# User Prompt

Record ID: 22
Source: Elbphilharmonie
Name: Orchester Wiener Akademie / Johanna Falkinger / Martin Haselböck
Date: Tue, 7 Apr 2026 20:00
Hall: Elbphilharmonie Großer Saal

Text to label:
Name: Orchester Wiener Akademie / Johanna Falkinger / Martin Haselböck
Program: Works by Johann Sebastian Bach, Georg Friedrich Telemann and others
Performers: Orchester Wiener Akademie / Johanna Falkinger / Martin Haselböck
Hall: Elbphilharmonie Großer Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

