# Tesoro, indizi, PNG e pericoli

Fonte: `dungeon_simulator/content.py`. Non sono tabelle del manuale come le
altre: sono i generatori che le tabelle dei contenuti chiamano quando un tiro
percentuale va a segno. **Nessuno di questi si vede sulla mappa**: stanno tutti
nel registro e nei tooltip.

## Tesoro

Il *tier* viene dal **livello del dungeon**, non dal livello del gruppo:

| livello | tier | gp | probabilità di oggetto magico |
|---|---|---|---|
| ≤1 | low | `d10 × 6` | 2% |
| 2-3 | mid | `d20 × 10` | 8% |
| 4-6 | high | `d20 × 50` | 20% |
| ≥7 | epic | `d20 × 200` | 40% |

Il moltiplicatore scritto nel codice è `(multiplier // 10) or 1` sui valori
60/100/500/2000, da cui i ×6, ×10, ×50, ×200 della tabella.

Un **hoard** (solo dal boss, e solo su un d20 ≥15) è un'altra cosa: `3d20 ×
(multiplier // 5)`, cioè ×12/×20/×100/×400, e con probabilità raddoppiata
(massimo 90%) porta `1d4` oggetti magici invece di uno.

Gli oggetti magici sono otto, pescati a caso da una lista fissa
(`_MAGIC_ITEMS`): pozione di guarigione, pergamena runica, pugnale +1, anello
che ronza, bacchetta con una carica, amuleto, mantello, arnesi da scasso.

## Indizi

`_CLUE_TABLE` è una **d100 vera**, cento voci scritte per esteso (indice 0 =
tiro 1). Un `assert` verifica che siano esattamente cento. Il punto finale della
voce viene tolto perché chi la usa aggiunge la propria punteggiatura.

Gli indizi arrivano da parecchie strade: macerie, cadaveri e corpi antichi nei
[passaggi](passage-contents.md), la maggior parte degli incontri, e il PNG che
sta indagando (che ne tira uno per dire *su cosa* sta indagando).

## PNG

`a level N <classe>`, dove N è `max(1, livello_suggerito + 1d4 - 2)` - quindi da
due sotto a uno sopra - e la classe è una fra dieci (`_NPC_CLASSES`, le classi
base). Chi chiama passa un suggerimento diverso a seconda del caso: il PNG
morente arriva un livello sotto, il PNG forte `livello + 1d4+1`.

## Pericoli

Un d6 secco (`_HAZARDS_D6`): voragine, funghi luminosi, **una trappola**,
crollo, mostro errante (difficoltà media), o scelta del giocatore.

Da notare: il risultato 3 dice solo *"a trap"* e **non tira** sulla
[Trap Table](trap.md). Un pericolo-trappola resta quindi senza DC e senza danno,
a differenza di una trappola vera pescata dai contenuti del passaggio.

## Incontri

`encounter_description` non genera nulla: restituisce
`Level-appropriate <difficoltà> encounter`. Le difficoltà (Easy, Medium, Hard,
Deadly) vengono dalle tabelle dei contenuti. **Non c'è nessuna tabella di
mostri**: la scelta della creatura è lasciata a chi gioca.

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.

- Il tier del tesoro segue il livello del dungeon e il danno delle trappole il
  livello del gruppo. È coerente con la fonte? Va verificato, perché le due
  scale divergono appena il gruppo scende di qualche livello.
- Il pericolo "a trap" del d6 dovrebbe probabilmente tirare sulla Trap Table.
