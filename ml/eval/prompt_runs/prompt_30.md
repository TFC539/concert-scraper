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

Record ID: 30
Source: Elbphilharmonie
Name: School Concert »HipHop Academy Hamburg & Ensemble Resonanz«
Date: Fri, 10 Apr 2026 11:00
Hall: Elbphilharmonie Großer Saal

Text to label:
Name: School Concert »HipHop Academy Hamburg & Ensemble Resonanz«
Program: String ensemble meets hip-hop crew: originating from Igor Stravinsky’s ballet »Apollon musagète«, the musicians of Ensemble Resonanz devise the new, crossover piece »Masters of Ceremony« with experts from the HipHop Academy in Hamburg Billstedt. Together, they ask what the ballet, premiered in 1928 in which the god Apollo dances with three muses, has got to do with us today and create new music from the original. The interplay of breakdancing, rap and string music produces such an extraordinary output, which is staged using scenery and visuals in the Grand Hall.
Performers: Ensemble Resonanz / Barbara Bultmann violin / Corinna Guthmann violin / Skaiste Diksaityte violin / Tom Glöckner violin / Tim-Erik Winzer viola / Maresi Stumpf viola / Saskia Ogilvie violoncello / Saerom Park violoncello / John Eckhardt double bass / HipHop Academy Hamburg / Franklyn (Slunch) Kakyire hip hop dance / Andy Calypso hip hop dance / Jenny Love hip hop dance / Marco (Mallekid) Baaden Breaking / Merve (Mer-C) Can Breaking / Grace (Gege) Owusu vocals / Sebastian (Sebó) Bosum rap / Amir (107 Amir) Dacic rap / Marlene Schleicher stage direction / Professor Niels (Storm) Robitzky choreography / Tobias Schwencke composition / George Brenner producing / Thorben Schumüller stage, costume / Charlotte Beinhauer script / Tim Dollmann musical advice Hip Hop
Hall: Elbphilharmonie Großer Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

