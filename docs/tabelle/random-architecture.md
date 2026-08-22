# Random Architecture Table (d20)

Fonte: `RANDOM_ARCHITECTURE_TABLE` in `tables.py`. Tirata solo dalla
[Passage Table](passage.md) 20. Riga di registro:
`[Architecture d20=N] <testo>`.

**Salvo una riga, tutta questa tabella è solo testo.** Il passaggio scrive la
voce e poi **ritira** sulla Passage Table come se avesse pescato un
"continue" - la caratteristica architettonica non occupa spazio sulla mappa e
non cambia la forma del corridoio.

| d20 | risultato | come lo interpreto |
|---|---|---|
| **1** | Statua | Solo testo. |
| **2** | Serie di alcove | Solo testo. **Da non confondere** con l'alcova delle [scale](stairs.md), che è una cosa diversa e disegnata. |
| **3** | Fontana | Solo testo. |
| **4** | 1d4 pozze | Solo testo - e il `1d4` **non viene tirato**: la riga arriva letterale. |
| **5** | Buco nel pavimento | Solo testo. Non è la caduta della riga 19 della Passage Table, che invece cambia livello. |
| **6** | Terrario sotterraneo | Solo testo. |
| **7** | Pilastri lungo i lati | Solo testo. |
| **8** | Catacombe | Solo testo. |
| **9** | Un enigma (prova di Intelligenza) | Solo testo, nessun tiro. |
| **10** | Plinto sacrificale | Solo testo. |
| **11** | Tempio / santuario | Solo testo. |
| **12** | Posto di guardia | Solo testo. |
| **13** | Botola con scala a pioli | Solo testo. **Non** genera scale né cambio di livello. |
| **14** | Corso d'acqua sotterraneo | Solo testo. |
| **15** | Caverna naturale | Solo testo. |
| **16** | Condotto di ventilazione | Solo testo. |
| **17** | Crescita cristallina | Solo testo. |
| **18** | Accampamento abbandonato | Solo testo. |
| **19** | **Portale** - porta in un'altra parte casuale del dungeon | **L'unica riga con effetto.** Si tira un d4: 1-2 passaggio, 3-4 stanza, e il figlio nasce in una **isola nuova**, cioè un blocco di mappa staccato sullo stesso livello. Il passaggio **finisce qui**. Sulla mappa, dove sta il portale, l'overlay disegna un **cerchio viola tratteggiato** con tooltip *"Portale - prosegue altrove sulla mappa"*. |
| **20** | Funghi / muschio commestibili | Solo testo. |

## Da indagare

> L'elenco completo di quello che le tabelle dicono e la mappa non sa ancora
> dire sta in [`TODO.md`](../../TODO.md), sezione 9.

Diverse righe descrivono qualcosa che avrebbe un posto sulla mappa - i pilastri,
le catacombe, la botola, il corso d'acqua, la caverna naturale. Oggi nessuna di
esse esiste come geometria. dungeongen ha dei *prop* propri (colonne, acqua) che
si potrebbero appendere alla cella del passaggio, come si fa con la scala.
