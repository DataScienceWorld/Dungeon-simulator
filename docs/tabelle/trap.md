# Trap Table (d100)

Fonte: `TRAP_TABLE` in `tables.py`. Interpretata da `content.roll_trap`.

Si tira quando qualcosa attiva una trappola: [Passage
Contents](passage-contents.md) 95-98, e [Secret Door](secret-door.md) 5-6.

**La fonte dice "make 4 rolls"**, e viene fatto alla lettera: quattro tiri per
ogni trappola, concatenati con *"; then "* in una sola riga di registro. Una
trappola è quindi quasi sempre una catena di quattro effetti diversi, e capita
che lo stesso tipo esca due volte.

**Niente di questa tabella si vede sulla mappa.** Una trappola non ha un
marcatore proprio: sta nella voce del passaggio o della stanza.

Ogni riga produce
`<tipo> (Notice DC N, Save DC M, Xd6 damage)`.

## Il danno

I dadi di danno **scalano col livello del gruppo** (`--party-level`, default 5),
non con il livello del dungeon:

- righe con `level_mod`: `max(1, livello + mod)` dadi;
- righe con `level_mult`: `max(1, ceil(livello × mult))` dadi.

| d100 | tipo | Notice | Save | dadi di danno (gruppo di livello L) |
|---|---|---|---|---|
| **1-6** | Poison darts | 11 | 10 | L-3 |
| **7-12** | Collapsing roof | 11 | 10 | L-2 |
| **13-19** | Simple pit | 11 | 11 | L-1 |
| **20-26** | Hidden pit | 11 | 12 | L-1 |
| **27-32** | Locking pit | 11 | 12 | L |
| **33-38** | Spiked pit | 12 | 13 | L |
| **39-44** | Rolling sphere | 12 | 14 | L |
| **45-50** | Scything blade | 13 | 14 | L+1 |
| **51-56** | Glyph trap | 14 | 15 | L+1 - **unica riga elementale**: si tira anche il tipo di danno fra fuoco, freddo, forza e fulmine, e finisce fra parentesi dopo il nome |
| **57-63** | Magic missile spell | 14 | 15 | L+1 |
| **64-69** | Poison gas / acid spray | 15 | 16 | L+1 |
| **70-76** | Room fills with water | 15 | 16 | L+2 |
| **77-82** | Walls begin closing | 16 | 17 | L+2 |
| **83-88** | Spears come out of the floor | 17 | 18 | L+2 |
| **89-93** | Spiked grate drops | 17 | 19 | **L×1.5** arrotondato per eccesso |
| **94-100** | Trapdoor (snakes / acid below?) | 18 | 20 | **L×2** |

## Da sapere

- Le trappole della [Door Table](door.md) **non passano da qui**: una porta
  trappolata tira solo la Percezione per accorgersene, e il danno non viene mai
  quantificato. È un'asimmetria della fonte, riprodotta com'è.
- Anche le due righe di coda (89-93 e 94-100) fanno **quattro tiri** come le
  altre: una "Trapdoor" può quindi accompagnarsi a tre effetti minori.
- `1-6 Poison darts` con un gruppo di livello 1 o 2 darebbe zero o meno dadi:
  il `max(1, ...)` lo tiene a uno.

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.
