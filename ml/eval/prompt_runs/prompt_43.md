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

Record ID: 43
Source: Elbphilharmonie
Name: Omer Klein & The Poetics
Date: Sat, 11 Apr 2026 20:00
Hall: Elbphilharmonie Großer Saal

Text to label:
Name: Omer Klein & The Poetics
Program: When the music of jazz pianist Omer Klein, born in Israel in 1982, is described as »borderless« (New York Times), this is meant quite literally: Klein composes for solo piano and big band, for jazz trio and orchestra, for theatre, dance and film. With the Omer Klein Trio, he has regularly generated enthusiasm in Hamburg in recent years. Now, Klein doubles his commitment – and returns to the Grand Hall with his newly-established sextet, The Poetics, featuring two saxophones and percussion.
Performers: Tineke Postma saxophone / Omri Abramov saxophone, flute / Omer Klein piano / Haggai Cohen-Milo bass / Tupac Mantilla percussion / Amir Bresler drums
Hall: Elbphilharmonie Großer Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

