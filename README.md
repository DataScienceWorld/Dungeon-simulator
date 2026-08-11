# Dungeon Simulator

Un generatore procedurale di dungeon in Python, basato sulle tabelle
d20/d100 per: dimensione e tipo del dungeon, area di partenza, passaggi,
porte, scale, stanze e relativi contenuti (trappole, tesori, indizi,
incontri, PNG, boss).

Il generatore "cammina" nelle tabelle esattamente come farebbe un
giocatore in solitario: parte da un'area iniziale e si espande
ricorsivamente (diramazioni di passaggi, porte, scale, uscite delle
stanze) finché non raggiunge il numero di stanze previsto dalla
dimensione tirata — a quel punto, come da regola della Dungeon Size
Table, le stanze smettono di avere uscite extra e i passaggi tendono a
finire in un vicolo cieco.

## Uso rapido

```bash
python3 main.py --seed 42
python3 main.py --seed 42 --format json -o dungeon.json
python3 -m dungeon_simulator --help
```

Opzioni principali:

- `--seed N` — seme per rendere il dungeon riproducibile.
- `--format text|json` — formato di output (default: testo indentato).
- `--verbose-empty` — mostra anche i risultati "vuoto" dei tiri sul
  contenuto dei passaggi (di default vengono omessi per leggibilità).
- `--limitless-cap N` — numero massimo di stanze usato quando la
  Dungeon Size Table tira "Limitless" (default 40).
- `--party-level N` — livello del party (default 5), usato dalla Trap
  Table per scalare i danni delle trappole.

## Struttura del progetto

```
dungeon_simulator/
  dice.py       # utilità per i tiri di dado (seedabili, espressioni "2d6+3")
  tables.py     # tutte le tabelle numeriche trascritte dal regolamento
  content.py    # generatori di tesori/indizi/PNG/trappole/pericoli
  models.py     # Node/Dungeon: l'albero del dungeon generato
  generator.py  # DungeonGenerator: la logica di esplorazione/dispaccio
  render.py     # rendering testuale e in dict (per il JSON)
  cli.py        # interfaccia a riga di comando
tests/          # test con pytest
```

## Tabelle implementate

- Dungeon Size Table (d20) e Dungeon Type Table (d10)
- Starting Area (d10)
- Passage Table (d20) e Passage Contents Table (d100)
- Door Table (d100)
- Stairs Table (d20)
- Room Table (d20, forme e dimensioni) e Room Contents Table (d100)
- Random Architecture / Feature Table (d20), incluso il Portale (voce 19)
  che ti sposta in un punto casuale del dungeon
- Secret Door Table (d6), con eventuale porta segreta trappolata
- Trap Table (d100, "make 4 rolls" come da regolamento — ogni innesco
  produce 4 componenti-trappola in sequenza, con danno scalato sul
  livello del party)
- Clue Table (d100, 100 indizi narrativi)

Alcune tabelle citate nel testo originale ma non incluse nelle pagine
fornite (tabella PNG, tabelle di tesoro individuale/hoard del DMG,
Tabella Ostacoli) sono state sostituite con generatori semplificati e
chiaramente isolati in `content.py`, così è facile collegare le
tabelle ufficiali se disponibili. Un paio di voci della tabella scale
(righe 18/19, entrambe "+15") e alcuni conteggi di uscite delle stanze
tagliati dallo scan originale (voci 19/20 della Room Table) sono
segnalati con un commento nel codice dove è stata fatta un'assunzione.

## Test

```bash
pip install pytest
python3 -m pytest tests/ -q
```
