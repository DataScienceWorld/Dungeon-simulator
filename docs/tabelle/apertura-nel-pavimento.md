# Apertura nel pavimento (d3)

Fonte: `FLOOR_OPENING_TABLE` in `tables.py`. Interpretata dal ramo `shaft` di
`DungeonGenerator._fill_passage`.

Si tira solo dalla [Passage Table](passage.md) **19**, *"Opening in the floor,
a straight drop down 1d10×10 ft"*: la riga dice che c'è un'apertura ma non che
cosa sia. Riga di registro: `[Opening d3=N] <testo>`.

Il tiro **non cambia la caduta** - la profondità è già stata tirata dalla riga
19 - e non cambia il bivio: da un'apertura nel pavimento si può sempre
scendere o tirare dritto, e sono due nodi. Cambia solo cosa si trova, e in un
caso se la via giù è raggiungibile.

| d3 | l'apertura è | come lo interpreto |
|---|---|---|
| **1** | Una trappola: il pavimento cede sotto di te | Si tira sulla [Trap Table](trap.md), quattro volte come vuole la fonte, e la riga `Trapped! ...` finisce nella voce del passaggio. La via giù resta aperta: la trappola è scattata, tu sei di sotto. |
| **2** | Una botola segreta - va trovata | Prova di Percezione **DC 15**, la stessa di ogni altra cosa nascosta qui. **Trovata**: `The trapdoor is found (Perception N vs DC 15)!` e la via giù esiste. **Non trovata**: la riga lo dice (`... the trapdoor goes unnoticed, and the way down with it.`) e **il ramo verso il basso non viene nemmeno generato** - resta solo la via dritta. Stesso trattamento di una porta segreta che nessuno nota: nel registro perché i dadi l'hanno prodotta, non sulla mappa perché nessuno l'ha vista. Su 60 seed: 27 botole, 17 non notate. |
| **3** | Un buco dove il pavimento ha ceduto | Niente di più: è lì e si vede. |

## Il bivio

Un'apertura nel pavimento è **due vie**, quindi due nodi:

- **giù**: d4, 1-2 passaggio e 3-4 stanza, al **livello successivo** - quindi
  un'isola nuova, disegnata su un'altra tavola;
- **dritto**: un passaggio allo stesso livello, che riparte dallo stesso punto.

Il passaggio finisce al bivio, come a un incrocio a T o a un passaggio
laterale. Prima scendeva e basta: il corridoio oltre l'apertura non esisteva
proprio, e sulla mappa la galleria si interrompeva senza che il registro
dicesse perché. Su 60 seed sono 97 aperture, 80 con due vie e 17 con una sola
(le botole non notate).

## Da indagare

Che una trappola tiri **quattro volte** sulla Trap Table è la convenzione della
fonte, applicata ovunque nel codice, ma qui la trappola *è* la fossa: quattro
effetti scollegati (dardi avvelenati, gas, lame) per un buco nel pavimento
leggono male. Va deciso se per questo caso ha più senso un tiro solo, o
nessuno con la caduta come unico danno.
