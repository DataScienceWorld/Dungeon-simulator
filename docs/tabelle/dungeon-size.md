# Dungeon Size Table (d20)

Fonte: `DUNGEON_SIZE_TABLE` in `tables.py`. Tirata **una volta sola**, per
prima, in `DungeonGenerator.generate`.

Decide il **budget di stanze** (`target_rooms`), che è il freno principale di
tutta la generazione.

| d20 | etichetta | stanze | come lo interpreto |
|---|---|---|---|
| **1-3** | Tiny | `1d4+2` | 3-6 stanze. |
| **4-8** | Small | `1d6+4` | 5-10 stanze. |
| **9-16** | Medium | `4d4+6` | 10-22 stanze. È l'intervallo più largo del d20: la maggior parte dei dungeon è media. |
| **17-18** | Large | `5d6+12` | 17-42 stanze. |
| **19** | Huge | `10d6+24` | 34-84 stanze. |
| **20** | Limitless | *(nessun numero)* | Non c'è un tiro: si usa il **tetto passato da fuori** (`--limitless-cap`, default 40). Senza un tetto la generazione non finirebbe. |

## Cosa succede quando il budget si esaurisce

È la regola della fonte: raggiunto il numero di stanze, le stanze smettono di
avere uscite in più e i passaggi tendono a finire in vicoli ciechi. Qui è
implementata così:

- Il controllo (`budget_exhausted`) avviene **al momento in cui un lavoro viene
  estratto dalla coda**, non quando viene accodato. L'esplorazione è in
  **ampiezza**, quindi tutti i nodi a profondità N sono risolti prima di
  qualsiasi nodo a profondità N+1, e il budget si consuma equamente fra rami
  fratelli invece di essere monopolizzato dal primo esplorato.
- Un nodo che trova il budget esaurito diventa un **nodo `edge`**, con una riga
  che dice esplicitamente *quale* limite è scattato:
  `[Budget di stanze esaurito: N/M] Il tiro qui sopra indicava una prosecuzione
  (stanza/passaggio/scale), ma questa simulazione ha già raggiunto il numero
  massimo di stanze previsto - non è un vicolo cieco previsto dalle tabelle.`
  Serve perché altrimenti si leggerebbe una contraddizione: *"ends in an open
  entrance to a room"* seguito da un vicolo cieco.
- Sulla mappa un `edge` è un **pallino grigio** preceduto da uno stub di
  corridoio da una cella, con tooltip *"Limite del dungeon"* (un vicolo cieco
  vero dice *"Vicolo cieco"*) e l'etichetta `#id` accanto, perché sul telefono i
  tooltip non si vedono.

## Gli altri due freni

- `--max-depth`: cappa i salti dall'ingresso. Scatta prima del budget e ha la
  sua riga: `[Limite di profondità raggiunto: max N nodi dall'ingresso] ...`
- `MAX_NODES = 4000`: rete di sicurezza assoluta, non pensata per scattare.

## Nota

Il budget conta **solo le stanze** (`rooms_created`), non i passaggi né le
porte. Un dungeon "Tiny" può quindi avere parecchi corridoi. E una stanza che il
layout non riesce a piazzare **ha già consumato il suo posto nel budget** -
mentre un ramo tagliato prima di essere tirato lo **restituisce**
(`_cut_branches_the_map_will_not_reach`).
