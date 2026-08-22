# Starting Area Table (d10)

Fonte: `STARTING_AREA_TABLE` in `tables.py`. Tirata **una volta sola**: è il
nodo radice, cioè da cosa si entra nel dungeon.

Il risultato viene passato a `dispatch_beyond` come qualunque altro "oltre",
quindi da qui in poi tutto procede con le tabelle normali.

| d10 | risultato | come lo interpreto |
|---|---|---|
| **1-2** | `passage` | Si entra in un corridoio: il primo nodo tira sulla [Passage Table](passage.md). |
| **3-4** | `room` | Si entra direttamente in una stanza: [Room](room.md) + [Room Contents](room-contents.md). |
| **5-6** | `door` | Si entra da una porta: [Door Table](door.md), con tutte le sue prove - si può quindi cominciare la partita davanti a una porta chiusa a chiave. |
| **7-8** | `stairs` | Si entra da una scala: [Stairs Table](stairs.md). **Il livello iniziale è 1 comunque**, e la scala lo cambia subito: un risultato "up one level" all'ingresso porta al livello 0, che esiste come tavola a sé. |
| **9-10** | `open_entrance` | Un'entrata aperta. Non è un tipo che il dispatch conosca, quindi si tira subito un **d4**: 1-2 passaggio, 3-4 stanza, e nel registro resta la riga *"Open entrance."* accanto al tipo e alla dimensione. Sulla mappa non c'è niente che distingua un'entrata aperta da un passaggio o una stanza qualsiasi. |

## Il nodo radice sulla mappa

Il nodo `start` non ha geometria propria: non occupa celle, non viene disegnato.
Il suo unico compito è dare ai figli un punto e una direzione di partenza. La
direzione iniziale e l'origine dell'isola vengono da `_LayoutWalker.walk_root`.

L'isola che contiene l'ingresso è marcata `is_entrance`, e serve al renderer per
sapere quale tavola mostrare per prima.

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.

Un'entrata aperta e un corridoio qualunque sono indistinguibili fra loro: il
d4 li rende la stessa cosa e la riga *"Open entrance."* resta l'unica traccia.
Il **punto** d'ingresso però è marcato - cerchio pieno ottone con l'etichetta
"Ingresso" sull'isola con `is_entrance`, cerchio tratteggiato con "Arrivo"
sulle altre - quindi manca solo la distinzione fra i cinque risultati, non il
segno.
