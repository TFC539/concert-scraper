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

Record ID: 28
Source: Elbphilharmonie
Name: MAJÄL مجال
Date: Thu, 9 Apr 2026 18:00
Hall: Laeiszhalle Studio E

Text to label:
Name: MAJÄL مجال
Program: The Arabic word MAJÄL مجال means area, space or possibility, depending on the context. The trio consists of Fadhel Boubaker (oud, Tunis), Matthias Kurth (guitar, Cologne) and Konrad Wiemann (percussion, Berlin). The sound of the Arabic lute is characteristic of MAJÄL’s music. Oud virtuoso Fadhel Boubaker elicits a wide variety of timbres from his instrument, and together with electric guitar and percussion, a delicate web of lively rhythms, strong melodies and jazz harmonies is created. The three musicians constantly switch roles and improvise within and sometimes outside their compositions, creating expressive music that ranges from jazz to rock to imaginary folklore – always with influences from Arabic maqam music. Please note: For organisational reasons, the concert has been relocated to Studio E of the Laeiszhalle. Please note: For organisational reasons, the concert has been relocated to Studio E of the Laeiszhalle.
Performers: Fadhel Boubaker oud Matthias Kurth guitar Konrad Wiemann percussion
Hall: Laeiszhalle Studio E
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

