# Room Table (d20) - forma e dimensioni

Fonte: `ROOM_TABLE_BUILDERS` / `roll_room_shape` in `tables.py`. Interpretata da
`DungeonGenerator._fill_room`, piazzata da `_LayoutWalker._walk_room`,
disegnata dal bridge (`_SHAPE_MAP`, `_MIN_ROOM_GRID_UNITS`).

Ogni riga della tabella tira **i propri dadi**: prima la forma/dimensione, poi
il numero di uscite. Righe di registro: `[Room d20=N] <testo>` e
`Exits: N (M beyond the way in)`.

| d20 | forma e dimensioni | uscite | come lo interpreto sulla mappa |
|---|---|---|---|
| **1-2** | Rettangolare, `1d4×10` × `1d4×10` ft | d6 | Rettangolo. |
| **3-4** | Quadrata, `(1d4+1)×10` ft di lato | d4 | Quadrato. |
| **5-6** | Quadrata, `(1d6+1)×10` ft | d6 | Quadrato. |
| **7-8** | Quadrata, `(1d8+1)×10` ft | d8 | Quadrato. |
| **9-10** | Rettangolare, `(1d4+1)×10` × `(1d8+1)×10` ft | d6 | Rettangolo. |
| **11-12** | Rettangolare, `(1d6+1)×10` × `(1d6+2)×10` ft | d6 | Rettangolo. |
| **13-14** | Circolare, `1d4×10` ft di diametro | d4 | **Cerchio vero** in dungeongen (`CIRCLE`). Il caso da 10 ft è quello che fa scattare l'ingrossamento minimo, vedi sotto. |
| **15** | Triangolare, `1d6×10` ft su un lato | d4 | **Disegnata rettangolare.** dungeongen non ha una forma triangolare: `_SHAPE_MAP` la manda su `RECT`. Il registro dice triangolare, la mappa mostra un rettangolo. |
| **16** | Poligonale, `1d4×10` ft di larghezza | `max(1, d4-2)` | **Ottagono** (`OCTAGON`). |
| **17** | Poligonale, `1d6×10` ft | `max(1, d4-1)` | Ottagono. |
| **18** | Poligonale, `1d6×10` ft | `max(1, d4-1)` | Ottagono. Riga identica alla 17 nella fonte. |
| **19** | Trapezoidale, ~`1d6×10` ft per lato | d4 | **Disegnata rettangolare** (`RECT`). Il numero di uscite non era leggibile nella scansione: si usa d4 per analogia con le altre stanze irregolari. |
| **20** | Caverna grezza, ~`1d12×10` ft | d6 | **Disegnata rettangolare** (`RECT`). Anche qui il numero di uscite era tagliato dalla scansione: d6 per analogia con stanze di dimensioni simili. |

## Le uscite

- Il numero tirato **include la via da cui si è entrati**: le uscite in più sono
  `exits - 1`. Se sono zero, il registro scrive esplicitamente
  `Exits: 1 (only the way in - no other exits)`.
- Ogni uscita in più prende uno **slot** ciclando `forward, right, left`: la
  prima davanti, la seconda a destra, la terza a sinistra, la quarta di nuovo
  davanti, e così via.
- Per ogni uscita si tira **d100, 50%**: `≤50` è una porta (che tira poi sulla
  [Door Table](door.md)), sopra è un'apertura senza porta. Il tiro **è scritto**
  (`[Room d100=N vs 50%] Exit k of m: ...`) anche quando il risultato è
  un'apertura semplice, perché altrimenti non lascerebbe traccia - e su 60 seed
  436 uscite su 1155 non arrivavano mai a essere riempite per esaurimento del
  budget.
- Ogni uscita occupa **una cella intera** della parete, e due non possono
  condividerla. Ciascuna ha la sua fascia di muro, con dentro una cella scelta
  in modo deterministico dall'id del figlio (stabile fra un render e l'altro,
  ma due uscite su una parete lunga non si allineano). **Se la parete non ha
  abbastanza celle, l'uscita non viene disegnata e il ramo si ferma**, con la
  riga `[Layout] La parete di questa stanza non ha abbastanza spazio...`.
- Un'uscita è registrata **anche quando oltre non c'è nulla di disegnabile**, in
  modo che il muro abbia comunque la sua breccia (`Exit` di dungeongen) e le
  icone dell'overlay non fluttuino accanto a un muro intero.

## Il piazzamento

- La stanza si piazza **dove il tiro l'ha messa**, in fondo al corridoio che
  la raggiunge. L'unica libertà è **dove lungo la parete d'ingresso** arriva
  quel corridoio: la porta resta ferma e la stanza scorre di lato. Si prova
  prima la posizione centrata, poi le altre in ordine di distanza.
- Uno scostamento di **20 ft o più** viene detto nel registro
  (`[Layout] L'ingresso di questa stanza si apre a circa Nft dal centro...`).
- **Se non entra in nessuna posizione, la stanza non viene piazzata.** Non si
  sposta niente. Il ramo si ferma con un tappo di vicolo cieco e la riga
  `[Layout] Non c'e' spazio sulla mappa per posizionare questa stanza...`; tiro,
  contenuto e figli restano nel registro.
- Una stanza non viene mai piazzata **sopra un corridoio già tracciato**. Chi
  disegna prima ha la precedenza.
- Due stanze possono **condividere un muro** (margine 0). Non è un difetto: il
  passaggio che le collega occupa comunque una cella sua.

## L'ingrossamento minimo

Una stanza più piccola di **2 celle** per lato (per esempio la circolare da
10 ft, che è larga come un corridoio) viene disegnata **ingrossata a 2 celle**,
ma solo se c'è spazio libero dove crescere: dove non c'è, si disegna alla sua
misura vera, piccola ma corretta. È un ritocco **solo grafico**: dimensioni
registrate, testo del log e calcoli di layout restano quelli veri.

## I contenuti

Il tiro sui contenuti è una tabella a parte: [room-contents.md](room-contents.md).
La **dimensione della stanza** però gli dà un bonus, e questo è qui perché
dipende dal tiro di forma: lato più lungo ≥130 ft → **+30**, ≥90 ft → **+15**,
altrimenti niente. Si somma all'eventuale bonus arrivato dalle scale.

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.
