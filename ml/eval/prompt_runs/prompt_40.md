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

Record ID: 40
Source: Elbphilharmonie
Name: Teatime Classics
Date: Sat, 11 Apr 2026 16:00
Hall: Laeiszhalle Kleiner Saal

Text to label:
Name: Teatime Classics
Program: In her early twenties, pianist Eva Gevorgyan already has an international concert career and performs regularly in the world’s major concert halls. This young charismatic lady particularly loves the romantic, highly virtuoso repertoire – she thereby also shines in the »Teatime Classics« series: all three composers on the programme were great pianists themselves, whose music packs a punch. While César Franck varies his audio material in all directions, Sergei Rachmaninov and Franz Liszt create vivid sound scenes, colourfully painted by Eva Gevorgyan. Franz Liszt Après une lecture du Dante, fantasia quasi Sonata / from: Années de pèlerinage, deuxième année, Italie, S 161 Sat, 11 Apr 2026 14:45 Coffee, tea and cake before the concert , Laeiszhalle, Brahms-Foyer
Performers: Eva Gevorgyan piano
Hall: Laeiszhalle Kleiner Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

