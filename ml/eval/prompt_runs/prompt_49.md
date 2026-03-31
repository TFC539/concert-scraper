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

Record ID: 49
Source: Elbphilharmonie
Name: Georg Friedrich Händel: Saul
Date: Sun, 12 Apr 2026 17:00
Hall: Laeiszhalle Großer Saal

Text to label:
Name: Georg Friedrich Händel: Saul
Program: Hardly any other work of Baroque music has such a clear-sighted impact on the present as George Frideric Handel’s oratorio Saul. Written in London in 1738, it tells the ancient story of the first king of Israel, whose jealousy of the young hero David leads to tragedy. But Saul is more than biblical history – it is a musical psychogram about power and humanity, about the dangerous pull of fame and the price of political vanity. Anyone looking today at the tensions between authority and change, old and new, will discover in Handel’s music an almost timeless reflection of our social and political upheavals. With luminous choruses, haunting arias, and orchestral drama, Handel creates a gripping psychological drama that goes far beyond the religious subject matter. The characters are impressively portrayed: the fanatical fury of the king, David’s gentle strength, Jonathan’s loyalty, Michal’s quiet love. Virtuoso choruses alternate with moving arias and instrumental surprises – including the organ, which Handel himself played. This tonal diversity creates a dramatic force that extends far beyond the sacred. Saul is a work about people in extreme situations – shockingly relevant in times of global power games, vulnerable democracies, and public spectacle. Handel’s music does not ask about winners or losers, but about human dignity in the storm of emotions. An oratorio that is more than a stage action: a musical mirror of our times. Saul is a work about people in extreme situations – shockingly relevant in times of global power games, vulnerable democracies, and public spectacle. Handel’s music does not ask about winners or losers, but about human dignity in the storm of emotions. An oratorio that is more than a stage action: a musical mirror of our times.
Performers: Symphonischer Chor Hamburg / Elbipolis Barockorchester Hamburg / Jonathan Michie bass / Tobias Hechler alto / Ilker Arcayürek tenor / Magdalene Harer soprano / Karola Sophia Schmid soprano / director Matthias Janz
Hall: Laeiszhalle Großer Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

