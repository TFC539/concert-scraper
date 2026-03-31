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

Record ID: 4
Source: Elbphilharmonie
Name: The Trumpet Shall Sound
Date: Wed, 1 Apr 2026 19:30
Hall: Elbphilharmonie Kleiner Saal

Text to label:
Name: The Trumpet Shall Sound
Program: The Matthias Höfs Trumpet Ensemble is made up of students and graduates from his trumpet class at the Hamburg University of Music and Theater. The trumpeters in this international ensemble include prize winners of international competitions, some of whom already hold top positions in leading symphony and opera orchestras such as the Berlin Philharmonic, the Tokyo Symphony, and the major German radio orchestras. Highly acclaimed recordings by this exceptional ensemble have already been released on the Berlin Classics label. With its own arrangements and compositions, the ensemble offers a concert program that showcases all the timbres of a wide variety of trumpet instruments with music ranging from Baroque to blues. Under the motto “The Trumpet Shall Sound,” works from Scheidt and Bach to modern composers are performed. works by Johann Sebastian Bach, Georg Friedrich Händel, Erik Morales, Itaru Sakai, Samuel Scheidt and others
Performers: Trompetenensemble Matthias Höfs
Hall: Elbphilharmonie Kleiner Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

