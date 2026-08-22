# Room Contents Table (d100)

Fonte: `ROOM_CONTENTS_TABLE` in `tables.py`. Interpretata da
`DungeonGenerator._room_contents_lines`.

Tirata **una volta per ogni stanza**, subito dopo forma e uscite. Riga di
registro: `[Room Contents d100=N]`, seguita da una o più righe di dettaglio.

## Il modificatore

Il tiro non è un d100 nudo: `modifier + size_bonus`.

- `modifier` arriva da chi ha dispatchato la stanza - [scale](stairs.md) con
  +15/+30, [porta segreta](secret-door.md) con +40/+50.
- `size_bonus` viene dalla stanza stessa: lato più lungo **≥130 ft → +30**,
  **≥90 ft → +15**, altrimenti 0.

Un totale che supera 100 **satura sull'ultima riga** (93-100, il boss), che è
esattamente quello che quei bonus devono fare: spingere verso il fondo della
tabella. Il numero scritto nel registro è il totale, quindi **può superare 100**
ed è normale.

## Cosa finisce sulla mappa

Il `tag` del risultato è l'unica parte che si vede: diventa il colore del
**pallino di gravità** disegnato nella stanza, e la sua voce in legenda.

| colore | etichetta in legenda | tag |
|---|---|---|
| rust | Pericolo grave / boss | `boss`, `deadly_encounter`, `bbeg_remnants`, `trapped_victim` |
| teal | Incontro | `encounter`, `dying_npc`, `creatures_fighting` |
| plum | Rischio / trappola | `strong_npc`, `hazard` |
| violet | Indizio / enigma | `relic`, `npc_investigating`, `runes` |
| slate | Vuota o poco rilevante | tutto il resto (`obstacle`, `empty_mission_loot`) |

Tutto il resto - tesoro, indizi, PNG - è **solo registro**, raggiungibile dal
tooltip della stanza.

## I risultati

Le percentuali nella colonna di destra sono tiri veri, fatti sul momento; quando
falliscono semplicemente non compare la riga.

| d100 | tag | come lo interpreto |
|---|---|---|
| **1-4** | `deadly_encounter` | Incontro Mortale. Extra: 45% tesoro, 75% indizio. Pallino **rust**. |
| **5-8** | `bbeg_remnants` | Tracce del boss - nessun tiro extra. Pallino **rust**. |
| **9-12** | `encounter` Facile | Con la nota "low-level minions of the BBEG". Nessun extra. Pallino **teal**. |
| **13-20** | `hazard` | Si tira il pericolo su d6 (voragine, funghi luminosi, trappola, crollo, mostro errante, scelta del giocatore). Pallino **plum**. |
| **21-32** | `encounter` Difficile | 30% indizio, 30% tesoro, **30% porta segreta**. Pallino **teal**. |
| **33-36** | `npc_investigating` | PNG generato + un indizio su cui sta indagando (due tiri, sempre presenti). Pallino **violet**. |
| **37-40** | `trapped_victim` | 30% che sia ancora vivo, 10% tesoro. Pallino **rust**. |
| **41-52** | `encounter` Facile | 20% tesoro, 10% porta segreta, 30% indizio. Pallino **teal**. |
| **53-56** | `obstacle` | Ostacolo che blocca la via. Solo testo, pallino **slate**. |
| **57-67** | `encounter` Medio | 30% tesoro, 20% porta segreta, 30% indizio. Pallino **teal**. |
| **68-71** | `dying_npc` | PNG in fin di vita, generato **un livello sotto**; 50% tesoro. Pallino **teal**. |
| **72-74** | `creatures_fighting` | d4 decide la difficoltà (≤2 Facile, altrimenti Medio). Pallino **teal**. |
| **75-76** | `runes` | Rune sul pavimento. Solo testo, pallino **violet**. |
| **77-80** | `strong_npc` | PNG forte, di livello `livello + 1d4+1`; un d4 decide l'atteggiamento (≤2 ostile-ma-trattabile, altrimenti offre alleanza). 30% porta segreta, 30% tesoro. Pallino **plum**. |
| **81-84** | `empty_mission_loot` | "Empty." più un 30% di tesoro. Pallino **slate**. |
| **85-88** | `encounter` Facile | 30% indizio, **30% PNG**, **30% dono minore** - le uniche due righe che usano `npc_pct`/`boon_pct`. Pallino **teal**. |
| **89-92** | `relic` | Reliquia sorvegliata da un incontro Mortale. Solo testo, pallino **violet**. |
| **93-100** | `boss` | Il boss. 90% di tesoro, e in quel caso un secondo d20: **≤14** → `1d4` tiri di tesoro normale, **≥15** → un **hoard** (tesoro molto più grande, con più oggetti magici). Pallino **rust**. |

## Nota sulle porte segrete di questa tabella

Le righe che tirano `secret_door_pct` scrivono *"There's a secret door hidden in
this room."* nel registro e **non disegnano niente**: non generano un nodo, non
aprono un muro, non mettono il marchio "S". Sono un aggancio narrativo, non una
via d'uscita. Le porte segrete che esistono davvero sulla mappa vengono dalla
[Door Table](door.md) 46-50 e dalla [Passage Table](passage.md) 6 e 14.
