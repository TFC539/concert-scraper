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

Record ID: 47
Source: Elbphilharmonie
Name: Workshop: Klassiko Orchestra Instruments
Date: Sun, 12 Apr 2026 12:00 / 14:00
Hall: Elbphilharmonie Kaistudio 2

Text to label:
Name: Workshop: Klassiko Orchestra Instruments
Program: This workshop offers a tour through the classical symphony orchestra. From the violin, cello and double bass to the trumpet and flute: participants can try them all out. And there are instruments in different sizes for youngsters and adults alike. To conclude the workshop, a little music-making session where everyone joins in shows that all the instruments harmonise. Please note: This workshop is aimed at families with children aged 6+. Children may only participate if accompanied by an adult guardian with a ticket. Children younger than six years may not participate in this workshop. If necessary, please switch to the workshop for children aged 4+. Please note: This workshop is aimed at families with children aged 6+. Children may only participate if accompanied by an adult guardian with a ticket. Children younger than six years may not participate in this workshop. If necessary, please switch to the workshop for children aged 4+.
Performers: 
Hall: Elbphilharmonie Kaistudio 2
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

