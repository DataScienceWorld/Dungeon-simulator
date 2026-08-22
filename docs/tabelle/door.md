# Door Table (d100)

Fonte: `DOOR_TABLE` in `tables.py`. Interpretata da
`DungeonGenerator._fill_door`, disegnata dal ramo `door` di
`_LayoutWalker._walk` e consegnata a dungeongen da `_door_type_at` /
`_door_kind`.

Riga di registro: `[Door d100=N] <testo>`, seguita dalle righe delle prove che
quel risultato comporta.

## Come si disegna una porta, qualunque sia il risultato

Il *risultato* decide il testo, le prove e cosa c'è **oltre**. Il disegno è
sempre lo stesso, e dipende da una sola cosa: se la porta è segreta o no.

- **La porta sta sul muro.** Non occupa nessuna cella e la camminata non avanza
  attraverso di essa (`node.geo["length_ft"] = 5`, ma quel 5 non diventa una
  cella come tutto il resto: è l'unica eccezione alla regola dei 10 ft). Il
  segmento registrato resta di una unità di griglia perché è ciò che dice su
  quale linea di muro si trova.
- Il percorso però **attraversa la soglia** (`path.points` avanza di una cella):
  senza, la cella finale del collegamento resta dalla parte sbagliata del muro,
  `_door_type_at` non riconosce la porta e la consegna come **aperta** - e in
  dungeongen una porta aperta non è un glifo, è un buco: fonde le due regioni e
  il muro sparisce. È così che due stanze che condividevano solo un muro sono
  venute fuori disegnate come una sola.
- **Ogni porta viene consegnata CHIUSA**, segrete comprese (`_door_kind`).
  dungeongen ha un tipo `SECRET`, ma il suo adattatore webview lo ripiega su
  `OPEN`, cioè su un buco: consegnare onestamente una porta segreta la
  trasformava nell'unica cosa che una porta segreta non deve essere,
  un'apertura.
- **Porta aperta** (`_door_type_at` non trova un nodo porta su quella cella):
  **non viene disegnato niente**, ed è giusto così. In dungeongen una porta
  aperta non è un glifo diverso, è un buco: `Map._trace_connected_region` ci
  passa attraverso, i due lati diventano una regione sola e su quel giunto non
  c'è nessun muro in cui mettere una porta. Su 12 seed sono 42 porte su 145 -
  la maggior parte dei giunti fra due tratti di corridoio.
- **Porta chiusa normale**: un **rettangolo disegnato sul muro** - riempito di bianco
  sopra il bordo, come fa il glifo di dungeongen per aprire il passaggio, e poi
  contornato - largo il 60% della cella e profondo un `border_width` per lato
  della linea. Più un rettangolo invisibile per il tooltip con tutto il testo
  della voce.

  Non è quello che disegnava dungeongen. Il suo glifo è costruito su una porta
  che ha **una cella tutta sua** fra le due cose che collega: i due "chip" di
  pavimento vanno dal centro di quella cella fino ai suoi due muri, e l'anta
  sta al centro, cioè in mezzo alla soglia. Le nostre porte stanno *sul muro* e
  non hanno cella, quindi entrambi i chip finivano dentro la cella del
  corridoio: quello dato all'elemento dall'altra parte del muro rientrava di
  **mezza cella** in una regione non sua e veniva contornato lì - la scatola
  arrotondata appiccicata al muro, con l'anta che galleggiava dentro, mezza
  cella lontano dal muro a cui appartiene. Misurato su 12 seed: 117 porte su
  117, e ogni anta a 0.50 celle dal muro. Ora 0 e 0
  (`_square_off_doors`).
- **Porta con una cella propria** (24 su 145 nella stessa misura, dove il
  corridoio non copre la cella): la soglia *è* quella cella, e il chip diventa
  un rettangolo che la attraversa, dato **intero a entrambi i lati** così i due
  contorni coincidono invece di lasciare una cucitura in mezzo. L'anta resta
  dove la mette dungeongen, che in questo caso è già il centro della soglia.
- **Apertura di stanza senza porta** (una stanza si apre su scale, un vicolo
  cieco o il bordo della mappa, e nessun collegamento stanza-stanza la copre):
  dungeongen riceve un `Exit`, che disegna *"a skewed inverted U archway
  extending away from the dungeon"* - una macchia nera in prospettiva **dentro
  la stanza**, contro il muro - e non apre niente: il muro dietro restava
  intero. È la "porta" che si vedeva fra la stanza 6 e il passaggio 13 del
  seed 72, dove il tiro diceva *"an open way through, no door"*. Ora al suo
  posto viene disegnato quello che il tiro ha detto: un **varco dipinto** sul
  muro se è un'apertura semplice (213 su 293 in 20 seed), la solita **porta
  rettangolare** se il layout ci ha messo un nodo porta (68), e **niente** se
  oltre non c'è pavimento scavato o se di là c'è l'alcova di una scala, che ha
  già la sua unica apertura (8). Vedi `_square_off_room_exits`.
- **Porta segreta** (`beyond == "secret"`): il muro **resta intero** e **non
  viene disegnata nessuna anta**. Prima ne veniva disegnata una: la porta
  segreta si vedeva come una porta qualsiasi, con la "S" sopra. Ora l'unico
  segno è il marchio **"S"** dell'overlay, con tooltip `Porta segreta. <testo>`.

## I risultati

`beyond` che compaiono: `room`, `passage`, `secret` (→ [Secret
Door](secret-door.md)), `d4_passage_stairs_room` (d4 1 passaggio, 2 scale, 3-4
stanza), `d4_passage_room` (d4 1 passaggio, altrimenti stanza).

| d100 | testo della tabella | come lo interpreto |
|---|---|---|
| **1-20** | Porta di legno rinforzata, non chiusa a chiave | Nessuna prova. Oltre: d4 passaggio/scale/stanza. Glifo di porta chiusa. |
| **21-25** | Grata di ferro con leva; d4 1-2 chiusa, 3-4 aperta; DC 14 arnesi, DC 19 Forza; la leva potrebbe essere trappolata | Nel registro: `Lock check: N vs DC 14` e `Forcing it open: N vs DC 19`, entrambi con esito. La leva "potrebbe essere trappolata" resta **solo testo** - non c'è tiro. Sulla mappa è una porta chiusa come le altre: la grata non ha un glifo suo. |
| **26-30** | Vano vuoto. Forse un glifo magico | Oltre: d4 passaggio/scale/stanza. Il "poco probabile" della fonte è reso con **35%** di trappola (`trap_chance_pct`), e se scatta si tira Percezione DC 15. **Attenzione**: è un vano *vuoto*, ma sulla mappa viene comunque disegnato il glifo della porta chiusa - il modello non ha un "arco senza porta" separato. Vedi *Da indagare*. |
| **31-35** | Porta di legno chiusa a chiave. DC 15, o sfondarla (AC 12, 20 hp) | `Lock check` DC 15. Oltre: stanza. |
| **36-40** | Porta di ferro chiusa a chiave. DC 14 | `Lock check` DC 14. Oltre: d4 passaggio/stanza. |
| **41-45** | Porta di pietra chiusa e trappolata. DC 15 per trovare la trappola | `Lock check` DC 15 **e** trappola al 100%, con Percezione DC 15. Due righe di prova. Oltre: d4 passaggio/scale/stanza. |
| **46-50** | Porta segreta. Oltre (d4) 1: passaggio nascosto, 2-4: camera nascosta | **L'unica riga che rende la porta segreta sulla mappa**: `geo["secret"] = True`, muro intero, marchio "S". Il d4 lo tira la [Secret Door Table](secret-door.md), che è ciò che sta davvero dietro. |
| **51-55** | Ingresso, poi 10 ft fino a un passaggio adiacente. Arco vuoto, nessuna porta | Oltre: passaggio. **Come sopra**: il testo dice "nessuna porta" ma il glifo viene disegnato lo stesso. Vedi *Da indagare*. |
| **56-60** | Porta di pietra con enigma. DC 14 Intelligenza | `Lock check` DC 14. Oltre: d4 passaggio/stanza. |
| **61-75** | Materiale e stato tirati a caso | Tre d6: materiale (1-2 legno, 3-4 pietra, 5-6 ferro), chiusa se d6≤3, trappolata se d6=1. Il risultato è **una riga in chiaro** nel registro (`Stone door, locked, untrapped.`). Sulla mappa non cambia niente: il glifo è lo stesso per tutti i materiali. |
| **76-80** | Porta trappolata. DC 15 per trovarla | Trappola al 100%, Percezione DC 15. Oltre: d4 passaggio/stanza. |
| **81-85** | Chiusa, apribile solo con una chiave portata da un umanoide nel dungeon | Riga di promemoria nel registro. Nessun tiro, nessun segno sulla mappa: la chiave non viene piazzata da nessuna parte. |
| **86-90** | Porta di energia elementale; passandoci si prendono 3d8 | Il danno **viene tirato** e scritto (`Passing through costs N damage.`). Sulla mappa è una porta chiusa. |
| **91-95** | Porta di pietra pesante, Atletica DC 16 | `Forcing it open` DC 16. Il "-1 hp ogni 2 fallimenti" resta testo. |
| **96-100** | Porta sfondata e fuori dai cardini | Nessuna prova. **Ancora una porta chiusa sul disegno**, anche se il testo dice il contrario. |

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.

Tre righe (26-30 "empty doorway", 51-55 "empty archway, no door", 96-100
"smashed and hanging off its hinges") descrivono una soglia **senza** un
battente, e vengono disegnate con il rettangolo di porta come tutte le altre.
Il glifo di porta *aperta* di dungeongen non è utilizzabile così com'è, perché
una porta aperta fonde le due regioni e cancella il muro. La strada praticabile
è ormai a un passo: `_square_off_doors` già riempie di bianco sopra il muro e
poi contorna: per una soglia vuota basta **non contornare**, esattamente come
per l'apertura dell'alcova delle scale. Non è fatto perché va deciso prima se
la distinzione si legge, a questa scala.
