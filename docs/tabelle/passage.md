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
| **6** | Dead ends. 40% chance of a secret door | Il 40% decide **se la porta c'è**. Se c'è, la prova di Percezione DC 15 decide soltanto **se qualcuno la nota**, e il registro lo scrive nei due modi; in entrambi i casi il figlio [Secret Door](secret-door.md) viene generato ed esplorato, dritto davanti. Se il 40% non passa: *"A true dead end."* In tutti i casi il passaggio finisce qui, con un **tappo grigio** e uno stub di corridoio da una cella perché il vicolo cieco si veda. |
| **7** | Continues 1d4×10 ft, then a four-way intersection | `move`, poi **tre** figli passaggio - sinistra, destra, dritto - e il passaggio **finisce all'incrocio**. Il "dritto" è un ramo come gli altri: prima veniva ripiegato nello stesso nodo e il terzo braccio non si leggeva da nessuna parte. |
| **8** | Continues 1d4×10 ft, then a T-junction | `move`, poi **due** figli, sinistra e destra. A una T non c'è un "avanti". Il passaggio finisce lì. |
| **9** | Continues 1d6×10 ft, then a side passage to the left | `move`, poi **due** figli: il passaggio laterale a sinistra, e il proseguimento dritto. Il passaggio finisce al bivio - la scelta fra i due è il punto della riga. |
| **10** | ...to the right | Come sopra, a destra. |
| **11** | Ends in an open entrance to a room | Nessuna lunghezza propria: scatta il minimo di 10 ft con la sua riga `[Layout]`. Poi un figlio `room` dritto davanti. **Nessuna porta**: sul disegno è un `Exit` di dungeongen sulla parete della stanza, cioè una breccia vera. |
| **12** | Door in the right wall. 50% il passaggio finisce qui | La porta è una **feature del muro laterale**, non la fine del passaggio: parte come **ramo di lato** (`turn` = destra) e il tronco *non* ruota. Poi si tira il 50% (`[Passage d100=N vs 50%]`, sempre scritto): se il passaggio prosegue, il proseguimento è **un secondo figlio** e il nodo finisce comunque qui. |
| **13** | Door in the left wall. 50% ... | Come sopra, a sinistra. |
| **14** | Secret door on a passage wall (DC 15). 50% ... | La porta **c'è**: la Percezione DC 15 dice solo se qualcuno la nota, e il ramo laterale verso [Secret Door](secret-door.md) viene esplorato in entrambi i casi. Il muro non è detto dalla tabella, quindi **si tira** (`[Passage d100=N] The secret door is in the left/right wall.`) e si scrive. Poi il 50% di proseguimento, come sopra. |
| **15** | Narrows to N ft wide | `max(5, (d6÷2)×10)` → 5, 10, 10, 20, 20, 30 ft secondo il d6 (misurato su 40 seed: escono tutti e quattro). Un d6 alto qui **allarga** invece di stringere - è la tabella che è fatta così. Vale tutto quello che è scritto sotto per l'allargamento: la larghezza resta da lì in poi, e **si ritira subito** sulla tabella passaggio. Stringersi però non si vede: un corridoio è già largo una cella e sotto non si può andare. |
| **16** | Widens to N ft wide | `max(10, (d6÷2)×10)` → **10, 20 o 30 ft** e nient'altro (misurato su 40 seed: 39/32/19). Da lì in poi **il passaggio resta di quella larghezza**, e la porta con sé anche oltre un bivio, giù per la via che tira dritto - non per un ramo che gira, che è un altro corridoio. Poi **si ritira subito** sulla tabella passaggio. Vedi sotto per cosa si vede e cosa no. |
| **17** | Opening to the left, leading to stairs. 50% ... | Apertura laterale, quindi **ramo di lato** verso `stairs`, tronco invariato. Sulla mappa: l'alcova delle scale con **la sua unica apertura dipinta sul muro verso il corridoio** - nessuna porta disegnata (vedi [stairs.md](stairs.md)). Poi il 50% di proseguimento. |
| **18** | Opening to the right, leading to stairs. 50% ... | Come sopra, a destra. |
| **19** | Opening in the floor, straight drop 1d10×10 ft | La lunghezza è **verticale**: nessun `move`, il passaggio non si allunga. **Due vie, quindi due nodi**: giù (d4 1-2 passaggio, 3-4 stanza, al **livello successivo**, cioè un'isola nuova su un'altra tavola) e dritto (un passaggio a questo livello, dallo stesso punto). Il passaggio finisce al bivio. Che cosa sia l'apertura si tira a parte: [apertura-nel-pavimento.md](apertura-nel-pavimento.md) - una trappola, una botola segreta da trovare, o un cedimento. |
| **20** | Roll on the Random Architecture table | Tiro su [random-architecture.md](random-architecture.md). Il risultato è **testo nel registro** e basta, tranne il 19 (*Portal*), che dispatcha un figlio in una **isola nuova** e mette un cerchio viola tratteggiato dove sta il portale. Negli altri casi il passaggio ritira e prosegue. |

## Cose che valgono per più righe

**Il minimo di una cella.** Diversi risultati non danno lunghezza al passaggio
(una porta nel muro, "ends in an open entrance"). Un passaggio è un luogo, non
una cerniera: avanza sempre di almeno `DEFAULT_PASSAGE_WIDTH_FT` = 5 ft, che
sulla griglia è **una cella da 10 ft**, e lo dice (`[Layout] Il tiro non dava
lunghezza propria al passaggio: sulla mappa percorre comunque il minimo di
10ft ...`). È la stessa regola dei 5 ft che diventano una cella, applicata
alla lunghezza.

**Ma non a un ridimensionamento che apre il passaggio.** Se il primo tiro è un
15 o un 16, quello non è un cambio a metà strada: è *quello che il passaggio
è*, e vale dalla prima cella. Prima il minimo veniva preso lì, alla larghezza
vecchia, e il passaggio 16 del seed 72 - che tira l'allargamento a 20ft e poi
"goes 15 ft and ends at a door" - veniva fuori largo 10ft per la prima cella e
20 per le altre due: tre celle di corridoio per un tiro che ne chiedeva due.
Su 40 seed, dei 101 passaggi che iniziano con un ridimensionamento **99 sono
ora un tratto solo** alla larghezza tirata; i due che non lo sono hanno un
secondo ridimensionamento più avanti. Prima: 5 tratti soli, e 43 con una cella
stretta appiccicata davanti.

**La larghezza resta.** Un tiro 15 o 16 non riguarda il tratto fino al bivio
successivo: riguarda **il passaggio**. La larghezza viene portata avanti in
`geo["width_ft"]` fino alla via che **tira dritto** - stesso corridoio - e non
giù per un ramo che gira, che è un corridoio nuovo alla larghezza ordinaria.
L'evento che marca la prosecuzione è `carries_on`, non `turn is None`: anche un
portale, una caduta e un figlio terminale hanno `turn: None`. Il nodo che
eredita lo scrive nella sua voce (*"This passage is N ft wide here, carried on
from the roll that changed it."*), perché il tiro che l'ha allargato sta in
un'altra voce. Su 20 seed i tratti larghi disegnati passano da 53 a 71.

**Dove si innesta la larghezza in più.** Un corridoio è largo una cella;
allargarlo aggiunge celle di fianco. **Due celle in più (30ft) si dividono in
parti uguali**, quindi il corridoio vecchio resta il centro di quello nuovo.
**Una sola (20ft) non si può dividere**, e da che parte va **si tira**
(`[Passage d100=N] The extra 10 ft goes on the left/right.`) - metterla sempre
dalla stessa parte piegherebbe tutti i corridoi larghi nello stesso verso. Su
40 seed: 24 a sinistra, 24 a destra. "Sinistra" è la sinistra guardando nel
verso di marcia, e il vettore `(dy, -dx)` la dà per ogni direzione senza una
tabella di casi (`_widened_cells`).

**Le celle di fianco sono sue.** Prima `_route_cells` rivendicava solo la linea
di mezzo qualunque fosse la larghezza, quindi un corridoio da 30ft ne
proteggeva un terzo e una stanza poteva essere costruita sopra il resto. Ora
rivendica tutta l'impronta. Costa: su 120 seed le stanze che il layout non
riesce a piazzare passano dal 14.9% al 15.9% - il prezzo del fatto che quel
terreno è davvero occupato.

**E se non c'è spazio, il passaggio si interrompe.** L'impronta viene fermata
contro le stanze già disegnate un passo alla volta (`_clip_wide_run`), fianchi
compresi. Un passaggio da una cella che arriva contro una stanza già disegnata
vi si apre come **ingresso segreto**; uno più largo **no** - una galleria da 20
o 30ft non è una porta nascosta - e si ferma lì con la sua riga `[Layout]`. Su
40 seed: 7 fermate così, contro 48 ingressi segreti tutti da passaggi di una
cella. La larghezza al momento dell'arrivo viaggia con l'uscita segreta
(`room_exits[...]["width"]`), perché rileggerla dai tiri del nodo sarebbe
sbagliato: un allargamento tirato *dopo* lo scontro resta nella voce anche se
la camminata non ci è mai arrivata.

**Ma un passaggio consegnato largo viene disegnato stretto.** Non c'è un
errore: `add_passage` accetta, la conversione riesce, e il campo `width` del
modello di layout **non viene mai letto** dall'adattatore. Misurato
consegnando lo stesso corridoio con `width` 1, 2 e 3: viene fuori sempre di
8x1 celle. (Un `ValueError` *esiste* - `Passage.__init__` rifiuta punti che
formino un rettangolo più largo di una cella, *"Passage must be exactly one
cell wide"* - ma l'adattatore costruisce sempre punti da una cella, quindi non
scatta mai.) Oggi la larghezza si vede quindi **solo nel renderer di ripiego
RoughJS**, che la disegna davvero, e mai nell'arte di dungeongen, che è quella
che si usa sempre.

La strada c'è ed è verificata: consegnare il tratto largo come una **stanza**.
Provato con stanza → passaggio → galleria 4x3 → passaggio → stanza: viene fuori
**una regione sola**, quindi nessun muro fra la galleria e i corridoi ai due
capi. Consegnare invece due corsie parallele da una cella **non** funziona:
misurate, restano due regioni distinte, quindi con un muro in mezzo. Vedi
[`TODO.md`](../../TODO.md) sezione 9.

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

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.
