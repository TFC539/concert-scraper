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

Record ID: 39
Source: Elbphilharmonie
Name: NDR Family Concert
Date: Sat, 11 Apr 2026 14:30 / 16:00
Hall: Rolf-Liebermann-Studio

Text to label:
Name: NDR Family Concert
Program: Three wind player friends make an appointment, clamp an oboe, clarinet or bassoon under one arm and the sheet music under the other – and off they go: with entertaining variations on a world-famous opera melody, cheerful folk dances and a lively »pleasure«, a divertimento by Wolfgang Amadeus Mozart.
Performers: Freya Linea Obijon oboe / Julius Ockert clarinet / Nicola Contini bassoon / Christina Ahrens-Dean scenography
Hall: Rolf-Liebermann-Studio
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

