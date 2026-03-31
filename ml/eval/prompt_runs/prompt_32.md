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

Record ID: 32
Source: Elbphilharmonie
Name: Klangzeit
Date: Fri, 10 Apr 2026 15:30
Hall: Albertinen Haus

Text to label:
Name: Klangzeit
Program: Listening to live music is a wonderful experience. In the »Klangzeit« (Sound Time) concerts, you can close your eyes and escape everyday life for a moment. In the entertaining, hour-long concerts featuring the string players of Ensemble Resonanz, you can listen in a relaxed atmosphere, express yourself, sing along to well-known songs and move freely. Here, everyone can be themselves. This makes the format particularly suitable for people with dementia and their relatives. All venues are accessible. »Die Spieluhr« Werke von Gioachino Rossini, Camille Saint-Saëns und Claudio Monteverdi Claudio Monteverdi L’incoronazione di Poppea / Dramma in musica in Prolog und drei Akten Dmitri Schostakowitsch Fünf Stücke für zwei Violinen und Klavier / Bearb. Benedict Ziervogel Johann Sebastian Bach Aria and a set of 30 variations / Clavier Übung IV, BWV 988 »Goldberg Variations« Camille Saint-Saëns Le cygne (The Swan) / from: Le carnaval des animaux (The Carnival of the Animals)
Performers: Ensemble Resonanz / Juditha Haeberlin violin / Benjamin Spillner violin / Swantje Tessmann viola / Jörn Kellermann violoncello / Benedict Ziervogel double bass / Vanessa Heinisch lute / Gregor Dierck, David Schlage, Franziska Stolz, Constantin Zill Concept
Hall: Albertinen Haus
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

