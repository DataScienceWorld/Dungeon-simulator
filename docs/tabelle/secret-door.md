# Secret Door Table (d6)

Fonte: `SECRET_DOOR_TABLE` in `tables.py`. Interpretata da
`DungeonGenerator.resolve_secret_door`.

Si tira quando qualcosa manda `beyond = "secret"`: la
[Door Table](door.md) 46-50, oppure la [Passage Table](passage.md) 6 (vicolo
cieco con porta segreta trovata) e 14 (porta segreta in una parete, trovata).

Riga di registro: `[Secret Door d6=N]`, e questa riga viene **messa in testa
alla voce del nodo che sta oltre**, non a una voce sua. Una porta segreta non ha
un nodo proprio, quindi non conta nemmeno come un passo di profondità: ciò che
sta oltre è alla stessa distanza dall'ingresso di come sarebbe senza.

| d6 | oltre | come lo interpreto |
|---|---|---|
| **1-2** | Stanza, **+40** al Room Contents | Una camera nascosta. Il +40 spinge il tiro contenuti verso il fondo: quello che si nasconde dietro una porta segreta vale la pena. |
| **3-4** | Passaggio, **+40** al Passage Contents | Un passaggio nascosto. |
| **5-6** | d4: 1 passaggio, altrimenti stanza; **+50**; **trappolata** | Il bonus più alto, e in più si tira subito la [Trap Table](trap.md) (quattro volte) e la trappola compare **prima** del resto nella voce: `[Secret Door d6=N] Trapped! ...`. |

## Cosa si vede sulla mappa

**Niente della porta in sé, oltre al marchio.** Il muro in cui è nascosta deve
sopravvivere: è tutto il punto di una porta segreta.

- Consegnata a dungeongen come porta **CHIUSA** (`_door_kind`), mai `SECRET` -
  il suo adattatore webview ripiega `SECRET` su `OPEN`, e una porta aperta non è
  un glifo ma un buco che fonde le due regioni e cancella il muro.
- L'overlay ci disegna sopra una **"S"** (`_secret_mark`), con tooltip
  `Porta segreta. <testo>`.
- Quando la porta segreta è invece un **ingresso segreto** - un corridoio che
  arriva contro una stanza già disegnata - non viene consegnato **nulla**: né
  porta né `Exit`. Il muro resta intero e la "S" è l'unica cosa che lo marca.
  L'`Exit` di dungeongen non andava bene perché non è una breccia neutra: la sua
  docstring lo descrive come *"a skewed inverted U archway extending away from
  the dungeon"*, cioè la via d'uscita disegnata in prospettiva, che spuntava
  sopra gli ingressi segreti.

## Da non confondere

*"There's a secret door hidden in this room."* del [Room
Contents](room-contents.md) **non passa da questa tabella** e non produce niente
sulla mappa: è un aggancio narrativo.
