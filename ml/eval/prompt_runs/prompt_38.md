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

Record ID: 38
Source: Elbphilharmonie
Name: Workshop: Kosmos Sound
Date: Sat, 11 Apr 2026 14:00
Hall: Elbphilharmonie Kaistudio 6

Text to label:
Name: Workshop: Kosmos Sound
Program: We don’t hear music with our ears alone: we can also experience it intensely with our whole body and with all our senses. In the workshop »Kosmos Klang« many special instruments are available for the purpose, such as sound chairs and vibrating water bowls. Participants experience the relaxing effect of the vibrations produced, and even make the sounds visible. Please note: This workshop is aimed at families with children aged 6+. Children may only participate if accompanied by an adult guardian with a ticket. Children younger than six years may not participate in this workshop. Please note: This workshop is aimed at families with children aged 6+. Children may only participate if accompanied by an adult guardian with a ticket. Children younger than six years may not participate in this workshop.
Performers: 
Hall: Elbphilharmonie Kaistudio 6
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

