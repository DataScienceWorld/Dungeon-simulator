# Passage Contents Table (d100)

Fonte: `PASSAGE_CONTENTS_TABLE` in `tables.py`. Interpretata da
`DungeonGenerator._passage_contents_lines`.

Tirata **dopo ogni singolo tiro** della [Passage Table](passage.md) - quindi un
passaggio che continua per cinque segmenti tira cinque volte i contenuti. Riga
di registro: `[Contents d100=N]` più il dettaglio.

**Niente di questa tabella si vede sulla mappa.** Un passaggio non ha pallino di
gravità come le stanze: il contenuto sta solo nel registro e nel tooltip.

Il modificatore può arrivare dalle [scale](stairs.md) (+15/+30) e satura
sull'ultima riga.

| d100 | tag | come lo interpreto |
|---|---|---|
| **1-69** | `empty` | Vuoto. **Nessuna riga**, a meno di `--verbose-empty`: sarebbe rumore su due terzi dei tiri. Il tiro è comunque avvenuto e ha consumato un numero della sequenza. |
| **70-80** | `rubble` | Macerie. **10%** che nascondano un indizio; altrimenti *"Just rubble."* |
| **81-84** | `corpse` | Un cadavere. **20%** di indizio addosso; altrimenti *"picked clean"*. |
| **85-88** | `old_body` | Un corpo morto da tempo. **40%** di indizio - la percentuale più alta delle tre. |
| **89-90** | `encounter` Facile | 15% tesoro, 15% indizio. |
| **91-92** | `encounter` Medio | 25% tesoro, 25% indizio. |
| **93-94** | `encounter` Difficile | 50% tesoro, 50% indizio. |
| **95-98** | `trap` | Trappola: si tira **quattro volte** sulla [Trap Table](trap.md), come vuole la fonte, e le quattro escono concatenate con *"; then "*. |
| **99-100** | `loot` | Tesoro fuori posto. **60%** che ci sia davvero (`Loot, oddly out of place here: ... How did this get here?`), altrimenti *"Nothing here after all."* Il `modifier: 30` e `treasure_rolls: 1` del payload **non vengono usati** da questo ramo di codice. |

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.

Il payload della riga 99-100 porta `treasure_rolls: 1` e `modifier: 30`, e
nessuno dei due viene letto: il codice tira un solo tesoro al livello corrente
senza bonus. Va deciso se il `modifier` doveva alzare il tier del tesoro o
rientrare in un tiro successivo, o se è avanzo della trascrizione.
