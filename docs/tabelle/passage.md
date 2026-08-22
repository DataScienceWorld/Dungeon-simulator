# Passage Table (d20)

Fonte: `PASSAGE_TABLE` in `tables.py`. Interpretata da
`DungeonGenerator._fill_passage`, poi disegnata da `_LayoutWalker._walk_passage`.

Tirata **in ciclo** dentro lo stesso nodo passaggio: i risultati "continue"
fanno ritirare subito, fino a `MAX_PASSAGE_SEGMENTS = 15` segmenti (oltre i
quali il registro scrive *"The passage keeps going, but you've mapped enough of
it for now."* e il ramo si chiude). Ogni tiro è seguito **sempre** da un tiro
sulla [Passage Contents](passage-contents.md), anche quando il passaggio finisce
subito.

Ogni tiro produce una riga `[Passage d20=N] <testo>` nella voce del passaggio.

| d20 | testo della tabella | come lo interpreto |
|---|---|---|
| **1** | Passage continues 1d4×10 ft | Evento `move`. Corridoio dritto di `1d4` celle nella direzione corrente. Il nodo **ritira subito**: è lo stesso passaggio che prosegue, non un nuovo nodo. |
| **2** | Goes 15 ft and ends at a door | `move` di 15 ft → **2 celle** (20 ft disegnati: 15 arrotonda a 2). Poi un figlio `door`, dritto davanti. La porta sta sul muro in fondo e non prende una cella sua. |
| **3** | Goes 30 ft and ends in stairs | `move` di 3 celle, poi un figlio `stairs` dritto davanti. Le scale ottengono la loro alcova: vedi [stairs.md](stairs.md). |
| **4** | Turns left 90° | Evento `turn`. Se il passaggio non ha ancora percorso niente, prima **avanza di una cella nella direzione vecchia** (riga `[Layout] Il tiro non dava lunghezza propria...`), poi ruota. Dopo la rotazione deve percorrere di nuovo almeno una cella prima di qualsiasi altra cosa, altrimenti due curve di fila si annullerebbero sulla mappa. Poi ritira. |
| **5** | Turns right 90° | Come sopra, dall'altra parte. |
| **6** | Dead ends. 40% chance of a secret door | Tiro al 40%. Se passa, prova di Percezione DC 15: **trovata** → figlio [Secret Door](secret-door.md) dritto davanti; **non trovata** → il registro dice che c'è ma nessuno la nota, e sulla mappa non c'è nulla. Se il 40% non passa: *"A true dead end."* In tutti i casi il passaggio finisce qui, con un **tappo grigio** e uno stub di corridoio da una cella perché il vicolo cieco si veda. |
| **7** | Continues 1d4×10 ft, then a four-way intersection | `move`, poi **tre** figli passaggio - sinistra, destra, dritto - e il passaggio **finisce all'incrocio**. Il "dritto" è un ramo come gli altri: prima veniva ripiegato nello stesso nodo e il terzo braccio non si leggeva da nessuna parte. |
| **8** | Continues 1d4×10 ft, then a T-junction | `move`, poi **due** figli, sinistra e destra. A una T non c'è un "avanti". Il passaggio finisce lì. |
| **9** | Continues 1d6×10 ft, then a side passage to the left | `move`, poi **due** figli: il passaggio laterale a sinistra, e il proseguimento dritto. Il passaggio finisce al bivio - la scelta fra i due è il punto della riga. |
| **10** | ...to the right | Come sopra, a destra. |
| **11** | Ends in an open entrance to a room | Nessuna lunghezza propria: scatta il minimo di 10 ft con la sua riga `[Layout]`. Poi un figlio `room` dritto davanti. **Nessuna porta**: sul disegno è un `Exit` di dungeongen sulla parete della stanza, cioè una breccia vera. |
| **12** | Door in the right wall. 50% il passaggio finisce qui | La porta è una **feature del muro laterale**, non la fine del passaggio: parte come **ramo di lato** (`turn` = destra) e il tronco *non* ruota. Poi si tira il 50% (`[Passage d100=N vs 50%]`, sempre scritto): se il passaggio prosegue, il proseguimento è **un secondo figlio** e il nodo finisce comunque qui. |
| **13** | Door in the left wall. 50% ... | Come sopra, a sinistra. |
| **14** | Secret door on a passage wall (DC 15). 50% ... | Il muro non è detto dalla tabella, quindi **si tira** (`[Passage d100=N] The secret door is in the left/right wall.`) e si scrive. Poi Percezione DC 15: **trovata** → ramo laterale verso [Secret Door](secret-door.md); **non trovata** → solo la riga nel registro, niente sulla mappa. Poi il 50% di proseguimento, come sopra. |
| **15** | Narrows to N ft wide | Larghezza `max(5, (d6//2)×10)` → 5, 10, 10, 20, 20, 30 ft secondo il d6. Un passaggio è largo **5 ft di default**, cioè **una cella**, quindi *stringersi* non si vede: `max(5,...)` e `max(10,...)` danno entrambi una cella. Un d6 alto qui **allarga** invece di stringere - è la tabella che è fatta così. Il corridoio viene comunque spezzato in due tratti dal punto del tiro in poi. Poi ritira. |
| **16** | Widens to N ft wide | `max(10, (d6//2)×10)` → 10, 10, 10, 20, 20, 30 ft. Si vede solo con **d6 ≥ 4**: sotto, 10 ft è già una cella come la larghezza di partenza. Con 20 o 30 ft il tratto viene davvero disegnato largo 2 o 3 celle. |
| **17** | Opening to the left, leading to stairs. 50% ... | Apertura laterale, quindi **ramo di lato** verso `stairs`, tronco invariato. Sulla mappa: l'alcova delle scale con **la sua unica apertura dipinta sul muro verso il corridoio** - nessuna porta disegnata (vedi [stairs.md](stairs.md)). Poi il 50% di proseguimento. |
| **18** | Opening to the right, leading to stairs. 50% ... | Come sopra, a destra. |
| **19** | Opening in the floor, straight drop 1d10×10 ft | La lunghezza è **verticale**: nessun `move`, il passaggio non si allunga. Il figlio (d4: 1-2 passaggio, 3-4 stanza) sta al **livello successivo**, quindi apre una nuova isola su un'altra tavola. Sulla mappa di questo livello resta solo la fine del passaggio. |
| **20** | Roll on the Random Architecture table | Tiro su [random-architecture.md](random-architecture.md). Il risultato è **testo nel registro** e basta, tranne il 19 (*Portal*), che dispatcha un figlio in una **isola nuova** e mette un cerchio viola tratteggiato dove sta il portale. Negli altri casi il passaggio ritira e prosegue. |

## Cose che valgono per più righe

**Il minimo di una cella.** Diversi risultati non danno lunghezza al passaggio
(una porta nel muro, "ends in an open entrance", un ridimensionamento prima di
qualsiasi movimento). Un passaggio è un luogo, non una cerniera: avanza sempre
di almeno `DEFAULT_PASSAGE_WIDTH_FT` = 5 ft, che sulla griglia è **una cella
da 10 ft**, e lo dice (`[Layout] Il tiro non dava lunghezza propria al
passaggio: sulla mappa percorre comunque il minimo di 10ft ...`). È la stessa
regola dei 5 ft che diventano una cella, applicata alla lunghezza.

**Il passaggio si ferma contro le stanze già disegnate.** Chi disegna prima ha
la precedenza. Se un passaggio raggiunge una stanza già piazzata, si ferma al
suo muro e vi si apre come **ingresso segreto** - una via d'accesso che nessuno
aveva previsto. Sulla mappa: nessun arco, il muro resta intero, e l'overlay ci
mette sopra una **"S"**. Tutto il resto di quel ramo non viene disegnato (la riga
`[Layout] Questo passaggio arriva contro la parete X della stanza #N...` lo
dice), ma resta nel registro. Se invece il passaggio *parte già dentro* la
stanza, non c'è muro contro cui fermarsi: non viene tracciato affatto, con la
sua riga.

**I rami laterali si attaccano al fianco della cella, non allo spigolo.** Un
ramo esce dalla parete laterale della cella in cui il passaggio si trova, e il
layout registra la cella di partenza (`_takeoff`) perché il bridge possa
ricongiungerlo al tronco: senza, dungeongen vede un passaggio da una cella che
sfiora un altro corridoio e ci mette un muro in mezzo.
