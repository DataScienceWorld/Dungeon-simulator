# Le tabelle generative, e come vengono interpretate

**Questi file vanno tenuti costantemente aggiornati.** Ogni volta che cambia
il modo in cui un tiro viene tradotto in registro o in mappa, la riga
corrispondente qui va corretta nello stesso commit. Servono a rispondere a una
sola domanda: *questo risultato del dado, sulla mappa e nel registro, cosa
diventa esattamente?*

Non sono la trascrizione delle tabelle - quella sta in
[`dungeon_simulator/tables.py`](../../dungeon_simulator/tables.py), ed è la
fonte. Qui accanto a ogni risultato c'è **l'interpretazione**: cosa viene
scritto nel log, cosa viene disegnato, e dove no.

| tabella | dado | file |
|---|---|---|
| Dungeon Size | d20 | [dungeon-size.md](dungeon-size.md) |
| Dungeon Type | d10 | [dungeon-type.md](dungeon-type.md) |
| Starting Area | d10 | [starting-area.md](starting-area.md) |
| Passage | d20 | [passage.md](passage.md) |
| Apertura nel pavimento | d3 | [apertura-nel-pavimento.md](apertura-nel-pavimento.md) |
| Passage Contents | d100 | [passage-contents.md](passage-contents.md) |
| Door | d100 | [door.md](door.md) |
| Stairs | d20 | [stairs.md](stairs.md) |
| Room (forma e dimensioni) | d20 | [room.md](room.md) |
| Room Contents | d100 | [room-contents.md](room-contents.md) |
| Random Architecture | d20 | [random-architecture.md](random-architecture.md) |
| Secret Door | d6 | [secret-door.md](secret-door.md) |
| Trap | d100 | [trap.md](trap.md) |
| Tesoro, indizi, PNG, pericoli | varie | [contenuti.md](contenuti.md) |

Documenti vicini: [`LESSONS.md`](../../LESSONS.md) per come funziona il
motore di disegno, [`TODO.md`](../../TODO.md) per quello che resta aperto.

Quello che le tabelle producono e la mappa **non sa ancora disegnare** - o
disegna come un'altra cosa - è raccolto in [`TODO.md`](../../TODO.md), sezione
9, tabella per tabella. Le note qui lo segnalano riga per riga e rimandano lì.

`tests/test_docs_tabelle.py` verifica che ogni riga di ogni tabella abbia la
sua riga qui, in entrambi i versi: una riga aggiunta a `tables.py` e non
documentata fa fallire la suite, e così una riga descritta qui che non esiste
più. Non può controllare la *prosa* - quella resta responsabilità di chi tocca
il codice.

---

## Convenzioni che valgono per tutte le tabelle

Da leggere una volta sola: le righe dei singoli file non le ripetono.

### La griglia

- **Una cella = 10 ft**, che è la risoluzione di dungeongen e non si può
  abbassare (`SCALE = 1`). Le tabelle però tirano davvero misure da 5 ft.
- **Ogni misura da 5 ft diventa una cella intera da 10 ft** (`_cells`,
  `_grid_cell_path`). Niente di ciò che i dadi hanno prodotto può arrotondarsi
  a zero: un passaggio da 5 ft si disegna lungo 10. Il registro continua a
  riportare i piedi veri.
- Conversione: `_cells(ft) = max(1, round(ft / 10))`. Quindi **15 ft → 2 celle
  (20 ft disegnati)**, 30 ft → 3 celle, 5 ft → 1 cella.
- **Unica eccezione: le porte.** Una porta sta *sul muro*, non è un tratto di
  corridoio: non occupa nessuna cella propria e la camminata non avanza
  attraverso di essa. Prima non era così, e una porta + passaggio senza
  lunghezza + seconda porta diventavano 30 ft di mappa per 5+0+5 tirati.

### Il registro

- **Tutto quello che i dadi hanno prodotto resta nel registro**, anche quando
  la mappa non lo disegna. Una stanza che non entra da nessuna parte ha
  comunque la sua voce, il suo contenuto e i suoi tiri.
- Quando la mappa non riesce a rappresentare qualcosa, lo dice in una riga
  `[Layout] ...` dentro la voce interessata - mai in silenzio.
- **Sinistra e destra nelle tabelle sono relative alla marcia** (è la
  convenzione narrativa del manuale). Sulla mappa nord-in-alto possono
  risultare dalla parte opposta, quindi il layout registra anche la direzione
  bussola vera (`approach_heading`).
- Dove c'è una scelta sulla mappa ci sono **due nodi nel registro**: quadrivio,
  T, passaggio laterale, e anche il "il passaggio prosegue oltre la porta nel
  muro". Prima il proseguimento veniva ripiegato nello stesso nodo e il bivio
  non si leggeva da nessuna parte.

### Cosa non viene disegnato, e perché

- **Una stanza che non entra non viene spostata: non viene piazzata.** Il ramo
  si ferma lì con un tappo di vicolo cieco e una riga `[Layout]`. Non si sposta
  mai niente per farlo entrare.
- **Un corridoio che arriva contro una stanza già disegnata si ferma al muro** e
  vi si apre come **ingresso segreto** (vedi [passage.md](passage.md)).
- **Un'apertura che non trova una cella libera sulla parete** viene lasciata
  cadere insieme al suo ramo (`_banded_wall_offset` → `None`): due aperture da
  10 ft non possono condividere la stessa cella.
- I rami che la mappa non potrà mai raggiungere vengono **tagliati prima** di
  spenderci sopra dei tiri (`_cut_branches_the_map_will_not_reach`), dopo ogni
  ondata in ampiezza. Una stanza tagliata torna nel budget.

### I muri, per capire i termini usati nelle righe

In dungeongen **non esiste un oggetto muro**: un muro è il contorno di una
regione. Due celle di pavimento contigue nella stessa regione non hanno niente
disegnato tra loro; due regioni che si toccano su una linea della griglia hanno
sempre un muro lì, e nessun "chip" può bucarlo - può solo aggiungere una gobba.
Un'apertura si ottiene o **fondendo le regioni**, o **dipingendo sopra il muro**
dopo che è stato tracciato. Il dettaglio sta in [`LESSONS.md`](../../LESSONS.md).
