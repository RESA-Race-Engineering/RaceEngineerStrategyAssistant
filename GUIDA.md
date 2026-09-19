# Guida rapida: prove, gara simulata e GUI

Serve solo Python 3.10 o più recente: nessun pacchetto da installare,
nessuna connessione internet per la GUI (solo per il feed Apex).

Nei comandi qui sotto `python` va adattato al sistema: su Windows
`.\.venv\Scripts\python.exe` (o `python`), su Linux e WSL `python3`.
Tutti i comandi vanno lanciati dalla cartella del progetto.

## 1. Aggiornare

```
git pull
```

## 2. Prove automatiche

```
python -m unittest discover -s tests
python main.py
```

Il primo comando deve finire con `OK`, il secondo con
`TEST COMPLETATO`. `main.py` scrive in `data/race_engineer.db`, che ora
è escluso da git.

## 3. Gara simulata

Il simulatore crea una gara finta di 6 ore nello stesso formato del
feed Apex: 16 squadre, 14 pit a testa, kart che girano fra le squadre,
una bandiera gialla fra 2:10 e 2:14. La gara è sempre la stessa, quindi
il file non è su git: si rigenera in un secondo.

```
python -m livetiming.simulate --out data/sim.jsonl
```

## 4. GUI sulla gara simulata

```
python -m gui --replay data/sim.jsonl --speed 60 --auto-pit --team "Scuderia Dante" --drivers "Marco,Luca,Andrea,Giulia,Paolo,Sara"
```

Si apre il browser su http://localhost:8765 (altrimenti aprirlo a mano).
`--speed 60` fa scorrere 6 ore in 6 minuti; `--auto-pit` conferma i pit
da solo. Questa modalità non scrive nel database. Per fermare: Ctrl+C.

Cosa guardare:

- **Barra in alto**: posizione, distacco, giro, tempo di gara e tempo
  mancante, bandiera, stato del feed. Il menu **Analisi** sceglie la
  finestra (ultimi N giri, stint, ultimi N minuti): vale insieme per
  noi, per i concorrenti e per il grafico.
- **Gara**: pilota e kart attuali, durata dello stint rispetto ai 45
  minuti, ultimo giro, media e migliore nella finestra, **prossimo pit**
  con la sua finestra. Grafico dei tempi nostro e di chi ci sta davanti e
  dietro, con "recuperiamo X s/giro, aggancio in N giri". In basso la
  linea degli stint con la finestra di pit e gli stint previsti.
- **Classifica**: tutte le squadre con le statistiche sulla finestra.
- **Piloti e stint**: tutta la gara colorata per pilota, passo di ogni
  pilota, tabella degli stint (clic su una riga per analizzarlo). Nella
  simulazione Paolo è volutamente il più lento.
- **Kart**: classifica dei kart calcolata sui giri di tutte le squadre
  (due kart simulati sono volutamente lenti).
- **Regole e registro**: controlli del regolamento, avvisi, pit, eventi.

Le medie escludono i giri "sporchi" (sopra il 107% della mediana: giro
con il pit, bandiera gialla), che nei grafici diventano triangoli in
alto.

### Provare il flusso del pit a mano

Senza `--auto-pit` e più lenta:

```
python -m gui --replay data/sim.jsonl --speed 10 --team "Scuderia Dante" --drivers "Marco,Luca,Andrea,Giulia,Paolo,Sara"
```

La gara parte da sola al via, con il primo pilota della lista (o
quello di `--start-driver`) e il kart del feed. A ogni PIT IN si apre da sola la
finestra del pit: si sceglie il nuovo pilota e si conferma; il kart
nuovo e la durata arrivano dal feed all'uscita dai box. I giri arrivati
nel frattempo restano in sospeso e finiscono nello stint giusto.

## 5. Il giorno della gara

Serve internet sul portatile (anche l'hotspot del telefono): il feed
arriva da `live-data.apex-timing.com`. La GUI in sé funziona offline.

**Prima della partenza**

1. `git pull` e le prove del punto 2.
2. Leggere il nome esatto con cui è iscritta la squadra:
   `python -m livetiming.watch --club kartandgo`
   (Ctrl+C per uscire; la colonna "Pilota" contiene il nome da usare).
3. Avviare la GUI con i piloti della squadra (in qualsiasi ordine: non
   è l'ordine degli stint, il pilota si sceglie a ogni pit) e un
   database solo per questa gara (AAAAMMGG = data della gara, vedi il
   punto 6):
   `python -m gui --team "NOME ESATTO" --drivers "Pilota1,Pilota2,Pilota3,Pilota4,Pilota5,Pilota6" --start-driver "Pilota di partenza" --db data/gara_AAAAMMGG.db`
   Se il browser non si apre (per esempio da WSL), aprire a mano
   http://localhost:8765. In alto deve comparire "Diretta · collegato" e,
   quando la griglia ha la squadra, sparisce "squadra non agganciata".
4. **La gara parte da sola.** Durante prove e qualifiche (titoli come
   "Prove", "Qualifiche") e con il cronometro fermo in griglia
   ("06:00:00") non succede niente; al via il primo stint si apre con
   il pilota di `--start-driver` (senza, il primo di `--drivers`) e
   con kart, giro e tempo presi dal feed. Si può aprire la GUI anche a
   gara iniziata: senza pit lo stint in corso parte da 0:00, dopo un
   pit dall'ultima uscita dai box (colonna "In pista", al minuto); se
   il kart è ai box si aspetta che esca. Il banner in alto dice che
   cosa si sta aspettando; **Avvia a mano** resta come ripiego, e con
   `--no-auto-start` si torna al solo pulsante **Avvia gara**.

**Durante la gara**

- A ogni PIT IN si apre la finestra del pit: scegliere il pilota e
  confermare, anche subito. Il kart non si inserisce: la squadra si
  segue per nome e il kart nuovo è quello che il feed indica
  all'uscita dai box (a Kart&Go il numero cambia durante la sosta,
  a volte due volte). Fino all'uscita il banner mostra il pilota scelto,
  che si può ancora cambiare. Accanto a ogni pilota ci sono stint e
  tempo di guida già fatti, per scegliere chi deve ancora guidare.
- Il campo kart serve solo se il feed non ha il kart: inserito a mano,
  vale quello. Se in seguito il feed indica un kart diverso compare un
  avviso: il dato non viene mai corretto da solo.
- Se compare l'avviso "i tempi dei giri sono sfasati" più di una volta,
  annotare l'ora: vuol dire che Apex aggiorna i tempi in un modo diverso
  da quello previsto.
- Se il feed cade: **Giro a mano** e **PIT** funzionano senza feed.
  Senza feed fin dall'inizio: aggiungere `--manual`.
- Se il programma si chiude:
  `python -m gui --resume --db data/gara_AAAAMMGG.db` riprende la gara
  dal database (stesso `--db` usato all'avvio).
- Per vedere la pagina dai telefoni sulla stessa rete: aggiungere
  `--host 0.0.0.0` (attenzione: da lì si possono anche confermare i pit).
- Se `config.js` di Apex non risponde: aggiungere `--apex-port 9230`
  (la porta di Kart&Go).

**Dopo la gara**

- **Esporta CSV** (oppure
  `python -m database.csv_export --db data/gara_AAAAMMGG.db`): cartella
  `data/export/gara_<id>`, file con `;` che si aprono in Excel.
- **Conservare `data/journal_<data>.jsonl`**: è la registrazione
  completa del feed e serve a verificare come Apex segnala giri e pit.

## 6. Il database

Il database è SQLite: un unico file, scritto dalla libreria standard di
Python. Per far girare il programma non serve installare nessun DBMS;
per consultarlo basta un programma che apra i file SQLite (DB Browser
for SQLite, DBeaver, ...).

**Cosa ci finisce e quando**

- In diretta e in modalità manuale la GUI scrive ogni giro, stint, pit
  ed evento nel momento in cui succede. In rilettura (`--replay`) non
  scrive niente.
- Senza `--db` il file è `data/race_engineer.db`, lo stesso in cui
  scrive `python main.py`: lì ci sono anche le gare di prova
  ("Test Race"). Per questo la gara vera va su un file suo, con `--db`
  (punto 5), e lo stesso `--db` va ripetuto con `--resume` e con
  `database.csv_export`.

**Non aprire il file mentre la GUI è accesa**

Se un altro programma tiene aperto il database mentre la GUI scrive,
la GUI trova il file bloccato ("database is locked"): non si chiude, ma
il giro o il pit di quel momento può mancare nel database. Aprirlo da
Windows attraverso `\\wsl$\...` è ancora peggio: su quel percorso i
blocchi di SQLite non sono affidabili e il file si può rovinare.

Durante la gara si lavora quindi su una copia. Questo comando la crea
in modo coerente anche con la GUI accesa:

```
python -c "import sqlite3; sqlite3.connect('data/gara_AAAAMMGG.db').backup(sqlite3.connect('data/copia.db'))"
```

La copia si apre senza rischi: da Windows, sullo stesso portatile, è in
`\\wsl$\Ubuntu\<cartella del progetto>\data\copia.db`; per un altro
computer si passa con una chiavetta o in chat. Per avere dati più
recenti si rilancia il comando, dopo aver chiuso la copia nel
programma che la stava leggendo.

**Senza un programma per SQLite**

Il pulsante **Esporta CSV** (punto 5, "Dopo la gara") funziona anche a
gara in corso: file con `;` che si aprono in Excel su qualsiasi
computer.

## Cosa è cambiato nel codice esistente

- `database/db.py`: tolti i metodi `update_stint_*` duplicati; nuovi
  `load_race()` e `get_last_race_id()`; `RaceDatabase(..., check_same_thread=False)`
  per l'uso dalla GUI, che gira su più thread; nuovo
  `update_pit_stop_duration()`, per la durata di un pit confermato
  mentre il kart era ancora ai box.
- `core/analytics.py`: le finestre valgono per tutta la squadra e non
  più per un solo kart (`get_laps_for_window` non prende più `kart_id`),
  lo "stint corrente" funziona anche con lo stint aperto, ci sono le
  finestre a tempo, i giri puliti e la tendenza.
- `core/strategy.py` (nuovo): finestra di pit, passo di piloti e stint,
  classifica dei kart.
- `gui/main_window.py` (vuoto) sostituito dalla GUI web in `gui/`.

## Limiti noti

Verificato su feed veri (Pomposa, Misanino, Kart&Go): collegamento,
griglia, colonne, formato del cronometro (millisecondi ogni 30 s).
Ancora da verificare, perché nessun kart girava: come Apex segnala giri,
pit e cambi kart. Il simulatore è una nostra ricostruzione; il journal
della gara vera è la cosa più utile da portare a casa.
