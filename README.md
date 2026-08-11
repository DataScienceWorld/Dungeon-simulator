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
python3 main.py --seed 42 --format html -o dungeon.html   # mappa 2D interattiva + registro
python3 -m dungeon_simulator --help
```

Il formato `html` apre una pagina con due viste: **Mappa** (una vera
pianta 2D — stanze numerate, corridoi, porte, scale, portali, con una
chiave numerata sotto la mappa e un tab per ogni livello del dungeon) e
**Registro** (l'albero testuale espandibile di tutti i tiri). La mappa
è ricostruita dalle stesse lunghezze, svolte e dimensioni già tirate
dal generatore (vedi `layout.py`), non è una rappresentazione separata:
passare col mouse su stanze/corridoi mostra i dettagli del tiro
corrispondente.

Il disegno di sfondo (muri, tratteggio, porte aperte/chiuse
inequivocabili) usa in modo opzionale
[dungeongen](https://github.com/benjcooley/dungeongen) (MIT), una
libreria Python dedicata al rendering di mappe da dungeon — se
installata e se il livello rientra nei suoi limiti dimensionali interni
(vedi sotto). Il nostro overlay interattivo (numeri di stanza, tooltip,
scale/portali/vicoli ciechi, la chiave sotto la mappa) resta sempre il
nostro, disegnato sopra lo sfondo di dungeongen nello stesso sistema di
coordinate: dungeongen viene usato solo per l'arte, mai per la
generazione o il posizionamento del contenuto, che restano interamente
quelli di `generator.py`/`layout.py`. Se dungeongen non è installato,
o un livello supera la sua soglia di sicurezza interna (dungeongen può
avere un crash nativo — non un'eccezione Python catturabile — su
geometrie troppo grandi), o un'isola del livello non ha nessuna stanza
(solo vicoli ciechi/bordi mappa, un caso che dungeongen non sa
rappresentare), quel livello ricade automaticamente sul renderer
alternativo interamente in SVG con [RoughJS](https://roughjs.com/)
(MIT, incorporato offline in `vendor/rough.min.js`, nessuna richiesta
di rete), che disegna con un tratto a mano libera invece di un
diagramma tecnico. Vedi `dungeon_simulator/dungeongen_bridge.py` per i
dettagli del bridge e delle soglie.

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
  models.py     # Node/Dungeon: l'albero del dungeon generato (con dati "geo" per la mappa)
  generator.py  # DungeonGenerator: la logica di esplorazione/dispaccio
  layout.py     # turtle-graphics: dall'albero generato a coordinate 2D per livello
  dungeongen_bridge.py  # traduce un'isola di layout.py nel modello Room/Passage/Door
                #   di dungeongen (opzionale) e ne richiede il rendering SVG di sfondo
  render_map.py # costruisce i dati della mappa; sfondo via dungeongen se disponibile
                #   e nei limiti, altrimenti fallback su RoughJS (disegno a mano libera)
  render.py     # rendering testuale, in dict (per il JSON) e HTML (mappa + registro)
  cli.py        # interfaccia a riga di comando
  vendor/       # RoughJS incorporato offline (MIT) - vedi vendor/NOTICE.md
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

## Dipendenze opzionali

Il generatore, il CLI e l'output `text`/`json` non hanno dipendenze
oltre alla libreria standard. L'output `html` funziona di default con
il solo renderer RoughJS (nessuna dipendenza extra).

Per abilitare anche il rendering di sfondo via dungeongen:

```bash
pip install -r requirements.txt
```

dungeongen si appoggia a `skia-python` (rendering nativo), che a sua
volta richiede le librerie grafiche di sistema `libegl1` e `libgl1`
(su Debian/Ubuntu: `apt-get install -y libegl1 libgl1`). Se
l'installazione o l'import di dungeongen fallisce per qualsiasi motivo,
`dungeongen_bridge.available()` ritorna `False` e la mappa HTML
continua a funzionare normalmente con il solo renderer RoughJS.

## Test

```bash
pip install pytest
python3 -m pytest tests/ -q
```

I test relativi a dungeongen (`tests/test_dungeongen_bridge.py`) si
saltano automaticamente se la libreria non è installata.
