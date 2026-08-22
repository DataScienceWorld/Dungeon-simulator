# Dungeon Type Table (d10)

Fonte: `DUNGEON_TYPE_TABLE` in `tables.py`. Tirata **una volta sola**, subito
dopo la [dimensione](dungeon-size.md).

| d10 | risultato |
|---|---|
| **1** | Lair |
| **2** | Tomb / Crypt |
| **3** | Abandoned stronghold |
| **4** | Temple or shrine |
| **5** | Natural caves |
| **6** | Maze |
| **7** | Mine |
| **8** | Planar Gate |
| **9** | Guild / cult headquarters |
| **10** | Death Trap |

## Come lo interpreto

**Come intestazione, e basta.** Il tipo compare nella prima voce del registro e
nel titolo della pagina, e **non influenza nessun altro tiro**: né le forme
delle stanze, né i contenuti, né la struttura dei corridoi. Un "Natural caves"
e un "Abandoned stronghold" con lo stesso seme producono lo stesso dungeon in
tutto tranne questa riga.

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.

È la tabella con il divario più grande fra quello che promette e quello che fa.
Le leve ovvie, se un giorno si vuole che conti:

- **Natural caves** dovrebbe spingere le forme di stanza verso `cave` e
  `polygon` invece che verso i rettangoli.
- **Maze** dovrebbe alzare la probabilità dei risultati di svolta e
  ramificazione sulla [Passage Table](passage.md).
- **Death Trap** dovrebbe alzare la frequenza di `trap` sui contenuti.
- **Tomb / Crypt**, **Temple** e **Mine** hanno corrispondenze evidenti nella
  [Random Architecture](random-architecture.md) (catacombe, santuario,
  condotti).

Nessuna di queste esiste. Prima di aggiungerle va deciso se la fonte le prevede
o se sarebbe una nostra invenzione - il resto del generatore è deliberatamente
fedele alle tabelle.
