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

Record ID: 20
Source: Elbphilharmonie
Name: Johann Christian Bach: Amadis de Gaule
Date: Mon, 6 Apr 2026 20:00
Hall: Elbphilharmonie Großer Saal

Text to label:
Name: Johann Christian Bach: Amadis de Gaule
Program: What happens when hatred, resentment, and jealousy interfere with the love between two people? When the light side of humanity also carries a dark side? The opera begins on the flip side of love, on the side of evil and with the confusion of the usual order. The evil sorceress Arcabonne confesses her shame at feeling something unfamiliar to her: love for the knight Amadis, who murdered her brother. A psychological portrait of four characters in two pairs now unfolds: the evil siblings Arcalaus and Arcabonne on the one hand, and Princess Oriane and Knight Amadis on the other. Caught between her murderous instinct and her desire, Arcabonne, incited by her brother Arcalaus, sows discord, strife, and mistrust between the two lovers, causing them to split up. Oriane turns away from her beloved Amadis because she disappointedly accuses him of infidelity. Amadis, on the other hand, feels misunderstood and rejected. The plot is straightforward, a classic knight’s tale with dragons, wizards, knights, and a rescued princess. However, the true plot in Johann Christian Bach’s work is not the one that is visible. It is the gradual transformation of the two characters, Amadis and Oriane, whose inner change becomes the actual subject of the opera. In trials, as in The Magic Flute, the audience witnesses the development of an ideal mediating couple. But why did this light-footed opera – sounding like early Mozart – fail at its premiere in Paris? Was the time not yet ripe for such music, was it the indecision between Italian and French opera traditions, or was it the recourse to a traditional subject? The opera »Amadis de Gaule« by the youngest son of Johann Sebastian Bach, who, like Handel, made his career in London and captivated audiences as a composer and concert organizer, touches a raw nerve with Parisian opera audiences in the pre-revolutionary year of 1779: it is a critique of lust and greed, hatred and envy, superficiality and hypocrisy that is presented here, symbolized by the opera business. It is one of the first Enlightenment operas for a bourgeois audience, but in 1779 opera was still a forum for the nobility. So when the revolution broke out ten years later, the opera houses were symbolically closed by the revolting people. The love felt by the evil sorceress, on the other hand, carries death within it. And so, because she cannot love Amadis and cannot kill him, the sorceress Arcabonne dies the first love death in the history of opera. In the end, however, the sublime, divine, pure love of the two protagonists, Oriane and Amadis, triumphs. But were there really two couples, or rather a single couple in two scenes? But why did this light-footed opera – sounding like early Mozart – fail at its premiere in Paris? Was the time not yet ripe for such music, was it the indecision between Italian and French opera traditions, or was it the recourse to a traditional subject? The opera »Amadis de Gaule« by the youngest son of Johann Sebastian Bach, who, like Handel, made his career in London and captivated audiences as a composer and concert organizer, touches a raw nerve with Parisian opera audiences in the pre-revolutionary year of 1779: it is a critique of lust and greed, hatred and envy, superficiality and hypocrisy that is presented here, symbolized by the opera business. It is one of the first Enlightenment operas for a bourgeois audience, but in 1779 opera was still a forum for the nobility. So when the revolution broke out ten years later, the opera houses were symbolically closed by the revolting people. The love felt by the evil sorceress, on the other hand, carries death within it. And so, because she cannot love Amadis and cannot kill him, the sorceress Arcabonne dies the first love death in the history of opera. In the end, however, the sublime, divine, pure love of the two protagonists, Oriane and Amadis, triumphs. But were there really two couples, or rather a single couple in two scenes? The love felt by the evil sorceress, on the other hand, carries death within it. And so, because she cannot love Amadis and cannot kill him, the sorceress Arcabonne dies the first love death in the history of opera. In the end, however, the sublime, divine, pure love of the two protagonists, Oriane and Amadis, triumphs. But were there really two couples, or rather a single couple in two scenes?
Performers: CPE.Bach.Chor.Hamburg / B’Rock Orchestra / Lenneke Ruiten soprano / Julia Sophie Wagner soprano / Ilker Arcayürek tenor / Krešimir Stražanac bass / director Hansjörg Albrecht
Hall: Elbphilharmonie Großer Saal
Source: Elbphilharmonie

Task:
Extract performers, program, and hall as normalized targets.

