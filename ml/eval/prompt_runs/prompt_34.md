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

Record ID: 34
Source: Elbphilharmonie
Name: Quatuor Arod
Date: Fri, 10 Apr 2026 19:30
Hall: Elbphilharmonie Kleiner Saal

Text to label:
Name: Quatuor Arod
Program: Haydn: String Quartet No. 75 / Bartók: String Quartet No. 5 / Tchaikovsky: String Quartet No. 1
Performers: Quatuor Arod
Hall: Elbphilharmonie Kleiner Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

