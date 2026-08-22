# Stairs Table (d20)

Fonte: `STAIRS_TABLE` in `tables.py`. Interpretata da
`DungeonGenerator._fill_stairs`, disegnata dal ramo `stairs` di
`_LayoutWalker._walk` e poi da `_quieten_stair_alcoves` nel bridge.

Riga di registro: `[Stairs d20=N] <testo>`.

## Come si disegna una scala, qualunque sia il risultato

Il *risultato* del d20 decide solo **dove si finisce** (quanti livelli su o giù,
e in cosa si sbuca). Il disegno è sempre lo stesso:

- Il nodo cammina 10 ft ed **emette un corridoio suo** (`stairs<id>`), perché i
  gradini hanno bisogno di un pavimento: prima l'84% delle scale stava sul nulla.
- La cella d'arrivo diventa una **stanza da una cella** - l'alcova - così ha
  muri propri. Come passaggio si sarebbe fusa con qualunque pavimento toccasse
  e li avrebbe persi.
- Dentro ci va la vera scala di dungeongen (`StairsProp`), rimpicciolita a
  `_ALCOVE_STAIR_SCALE` perché il gradino più largo non finisca sulla soglia.
- **Nessuna porta viene disegnata.** La porta esiste (chiusa, legata al
  passaggio d'accesso) solo per tenere l'alcova una regione a sé; l'apertura è
  **dipinta sopra il muro** dopo che il bordo è stato tracciato. Risultato: un
  quadrato da 10 ft, tre muri, **una sola apertura**, dal lato da cui si arriva.
  Misurato su 20 seed: 112 alcove su 112.
- Sopra la cella l'overlay scrive la nota **`(<id destinazione> L<livello>)`** -
  in che stanza/passaggio si sbuca e a che livello - più un rettangolo
  invisibile per il tooltip.
- Se la cella dell'alcova cade dentro una stanza già disegnata **l'alcova non
  viene creata** (sarebbero due stanze sovrapposte); la scala viene comunque
  consegnata e i gradini si disegnano lo stesso. Idem se due scale finiscono
  sulla stessa cella: la seconda non ha alcova.

Il **verso dei gradini** è quello di salita: scendendo, è all'indietro rispetto
alla marcia.

## I risultati

`beyond` che compaiono: `d4_room_passage` (d4 1-2 stanza, 3-4 passaggio),
`d4_passage_room` (d4 1 passaggio, altrimenti stanza), `room`, `passage`.

| d20 | testo della tabella | come lo interpreto |
|---|---|---|
| **1-8** | Down one level to a (d4) room/passage | Livello +1. Il figlio nasce su una **isola nuova**, disegnata su un'altra tavola: sulla mappa di questo livello si vede solo l'alcova con la nota. |
| **9** | Down one level to a room, +15 al Room Contents | Livello +1, figlio stanza, e il **+15 va al tiro contenuti** della stanza (spinge verso il fondo della tabella, cioè verso i risultati migliori). |
| **10** | Down one level to a room, +30 | Come sopra con +30. |
| **11** | Down one level to a passage | Livello +1, figlio passaggio. |
| **12** | Down one level to a passage, +15 | Il +15 va al **Passage Contents** del figlio. |
| **13** | Down one level to a passage, +30 | Come sopra con +30. |
| **14** | Down two levels to a (d4) passage/room | Livello +2: si salta un livello, e la nota sulla mappa dice L+2. |
| **15** | Up one level to a room, +15 | Livello -1. |
| **16** | Up one level to a room, +30 | Come sopra con +30. |
| **17** | Up one level to a passage | Livello -1. |
| **18** | Up one level to a passage, +15 | Livello -1, +15 al Passage Contents. |
| **19** | Up one level to a passage, +15 | **Trascritto come stampato**: la fonte ripete +15 anche qui, dove ci si aspetterebbe +30. |
| **20** | Up two levels to a (d4) passage/room | Livello -2. |

## Da sapere

- Il bonus (`modifier`) viaggia **con il dispatch**, quindi arriva al tiro
  contenuti del figlio, non a quello delle scale. Un bonus che supera il fondo
  della tabella **satura sull'ultima riga**, che è esattamente ciò che deve fare.
- `_convert_stair` di dungeongen non è affidabile per piazzare i gradini: cerca
  un passaggio, poi una stanza, poi ripiega su `passages[0]` e li mette su un
  corridoio senza rapporto. `_quieten_stair_alcoves` glieli toglie e li
  ridisegna.
