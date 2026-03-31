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

Record ID: 21
Source: Elbphilharmonie
Name: Bee Gees by MainCourse
Date: Tue, 7 Apr 2026 19:30
Hall: Laeiszhalle Großer Saal

Text to label:
Name: Bee Gees by MainCourse
Program: When you hear the first notes with your eyes closed, you could swear it was Barry, Robin, and Maurice standing on stage singing their world-famous hits. But it’s not the Bee Gees who are taking the audience on a musical journey through their decades-long successful career. It’s the Dutch band MainCourse – phenomenal winners of the TV talent show »The Tribute – Battle of the Bands« in 2024. But MainCourse goes far beyond a tribute show: they transport the magic of yesteryear into the present, with the energy of 2025 and the power of a band that makes concert halls shake. Their shows are not mere imitations, but a thrilling experience that puts the timeless hits of the Bee Gees in a contemporary light.
Performers: MainCourse band
Hall: Laeiszhalle Großer Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

