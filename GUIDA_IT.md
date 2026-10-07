# Race Engineer Strategy Assistant — Guida all'utilizzo

Questa guida spiega come testare il progetto, eseguire una gara simulata e utilizzare l'applicazione durante una gara reale.

È richiesto Python 3.10 o superiore. Non sono necessari pacchetti aggiuntivi.

Tutti i comandi devono essere eseguiti dalla cartella del progetto.

Su Windows, sostituire `python` con `.\.venv\Scripts\python.exe` (oppure `python`).
Su Linux e WSL, usare `python3` se necessario.

## 1. Aggiornare il progetto

Prima di eseguire test o utilizzare il programma durante una gara:

```bash
git pull
```

## 2. Eseguire i test

Eseguire i test automatici:

```bash
python -m unittest discover -s tests
```

Il comando dovrebbe terminare con:

```text
OK
```

È inoltre possibile eseguire il programma principale di test:

```bash
python main.py
```

Dovrebbe terminare con:

```text
TEST COMPLETATO
```

`main.py` scrive nel file `data/race_engineer.db`, che è escluso da Git.

## 3. Eseguire una gara simulata

Il simulatore genera una gara di sei ore utilizzando lo stesso formato del feed Apex.

La simulazione comprende:

* 16 squadre
* 14 pit stop per squadra
* Kart che ruotano tra le squadre
* Una bandiera gialla tra le 2:10 e le 2:14

La simulazione è deterministica, quindi il file non deve essere salvato su Git e può essere rigenerato in qualsiasi momento.

```bash
python -m livetiming.simulate --out data/sim.jsonl
```

## 4. Avviare la GUI con la simulazione

Avviare la GUI utilizzando la gara simulata:

```bash
python -m gui --replay data/sim.jsonl --speed 60 --auto-pit --team "Scuderia Arcobaleno" --drivers "Marco,Dante,Massimo,Mario,Luigi,Yoshi"
```

La dashboard viene aperta all'indirizzo:

```text
http://localhost:8765
```

Se il browser non si apre automaticamente, aprire manualmente l'indirizzo.

Con `--speed 60`, la gara di sei ore viene eseguita in circa sei minuti.

`--auto-pit` conferma automaticamente i pit stop.

Questa modalità non scrive nel database.

Per interrompere l'applicazione, premere `Ctrl+C`.

### Cosa controllare

**Barra superiore**

Mostra le principali informazioni sulla gara:

* Posizione
* Distacco
* Giro
* Tempo di gara e tempo rimanente
* Bandiera
* Stato del feed

Il menu **Analisi** permette di scegliere la finestra di analisi: ultimi N giri, stint corrente o ultimi N minuti. La finestra selezionata viene applicata alla squadra, ai concorrenti e ai grafici.

**Gara**

Mostra:

* Pilota e kart attuali
* Durata dello stint rispetto al limite di 45 minuti
* Ultimo giro, media e miglior tempo nella finestra selezionata
* Prossimo pit e relativa finestra
* Confronto del passo con le vetture davanti e dietro
* Tempo di recupero stimato e numero di giri necessari per raggiungere la vettura davanti
* Timeline degli stint, comprese le finestre dei pit e gli stint previsti

**Classifica**

Mostra tutte le squadre e le relative statistiche per la finestra di analisi selezionata.

**Piloti e stint**

Mostra l'intera gara suddivisa per pilota, il passo di ogni pilota e una tabella degli stint.

Cliccando su uno stint è possibile analizzarlo.

Nella simulazione, Paolo è volutamente il pilota più lento.

**Kart**

Mostra la classifica dei kart calcolata sui giri registrati da tutte le squadre.

Due kart simulati sono volutamente più lenti degli altri.

**Regole e registro**

Mostra i controlli del regolamento, gli avvisi, i pit stop e gli eventi della gara.

### Filtro dei giri

Le medie e le analisi del passo escludono i giri sporchi.

Un giro viene considerato sporco quando supera il 107% della mediana dei tempi sul giro, ad esempio a causa di un pit stop o di una bandiera gialla.

I giri sporchi vengono mostrati nei grafici come triangoli nella parte superiore.

### Testare manualmente il flusso dei pit stop

Per testare manualmente i pit stop, rimuovere `--auto-pit` e ridurre la velocità della simulazione:

```bash
python -m gui --replay data/sim.jsonl --speed 10 --team "Scuderia Arcobaleno" --drivers "Marco,Dante,Massimo,Mario,Luigi,Yoshi"
```

All'inizio, la finestra per la scelta del pilota si apre automaticamente.

Quando viene rilevato un **PIT IN**, si apre automaticamente la finestra del pit. Selezionare il pilota successivo e confermare la sosta.

Il nuovo kart e la durata dello stint vengono presi dal feed quando il kart esce dai box.

I giri ricevuti mentre il pit viene elaborato rimangono in sospeso e vengono assegnati allo stint corretto una volta completata la sosta.

## 5. Il giorno della gara

Per ricevere il feed Apex è necessario avere una connessione Internet sul portatile. È sufficiente anche l'hotspot del telefono.

La dashboard funziona localmente e non richiede una connessione Internet.

### Prima della gara

1. Aggiornare il progetto ed eseguire i test descritti nella Sezione 2.

2. Controllare il nome esatto della squadra registrato nel sistema di cronometraggio:

```bash
python -m livetiming.watch --club "NOME ESATTO KARTODROMO"
```

Premere `Ctrl+C` per uscire.

Utilizzare esattamente il nome mostrato nel sistema.

3. Avviare la GUI con il nome della squadra e tutti i piloti:

```bash
python -m gui --team "NOME ESATTO" --drivers "Pilota1,Pilota2,Pilota3,Pilota4,Pilota5,Pilota6" --db data/gara_AAAAMMGG.db
```

L'ordine dei piloti non determina l'ordine degli stint. Il pilota viene scelto a ogni pit stop.

Se il browser non si apre automaticamente, aprire:

```text
http://localhost:8765
```

Nella barra superiore dovrebbe comparire:

```text
Diretta · collegato
```

Quando la squadra viene trovata nella griglia di partenza, il messaggio relativo alla squadra non agganciata scompare.

4. Selezionare il pilota di partenza.

Il via della gara viene determinato dal feed. Il pilota di partenza viene selezionato manualmente tramite **Scegli pilota di partenza**.

È possibile farlo prima o dopo la partenza.

Durante prove e qualifiche, e mentre il cronometro è fermo sulla griglia, i dati di gara non vengono elaborati. Al via, il tempo di gara, il giro e il kart vengono presi dal feed.

Se non è stato selezionato un pilota di partenza, la finestra di selezione si apre automaticamente e i giri ricevuti rimangono in sospeso fino alla scelta del pilota.

Il primo stint inizia comunque dalla partenza effettiva della gara.

Se la GUI viene avviata quando la gara è già iniziata:

* senza un pit precedente, lo stint corrente parte da `0:00`;
* dopo un pit, parte dall'ultima uscita dai box;
* se il kart è ancora ai box, l'applicazione attende che esca.

Il banner superiore mostra cosa sta aspettando l'applicazione.

È inoltre possibile inserire manualmente un kart per avviare immediatamente la gara.

Con `--no-auto-start` è possibile disabilitare l'avvio automatico e utilizzare nuovamente il pulsante **Avvia gara**.

### Durante la gara

**Pit stop**

A ogni **PIT IN**, la finestra del pit si apre automaticamente.

Selezionare il pilota successivo e confermare la sosta.

Normalmente non è necessario inserire manualmente il numero del kart. La squadra viene seguita tramite il nome e il nuovo kart viene ricavato dal feed quando esce dai box.

A Kart&Go, il numero del kart può cambiare durante la sosta, anche più di una volta.

Fino all'uscita dai box, il pilota selezionato viene mostrato nel banner e può ancora essere modificato.

Per ogni pilota vengono inoltre mostrati il numero di stint completati e il tempo di guida già effettuato, per facilitare la scelta del pilota successivo.

**Inserimento manuale del kart**

Il campo kart è necessario solo quando il feed non fornisce il numero del kart.

Se viene inserito manualmente un kart e successivamente il feed ne indica uno diverso, viene mostrato un avviso. Il valore inserito manualmente non viene mai modificato automaticamente.

**Avvisi sui tempi**

Se l'avviso **i tempi dei giri sono sfasati** compare più di una volta, annotare l'orario.

Questo indica che Apex potrebbe aggiornare i tempi sul giro in modo diverso da quello previsto.

**Perdita del feed**

Se il feed live si interrompe, **Giro a mano** e **PIT** possono comunque essere utilizzati.

Per eseguire la gara interamente senza feed, avviare l'applicazione con:

```bash
python -m gui --manual
```

**Riavvio dell'applicazione**

Se l'applicazione si chiude, è possibile riprendere la gara utilizzando lo stesso database:

```bash
python -m gui --resume --db data/gara_AAAAMMGG.db
```

**Accesso da altri dispositivi**

Per accedere alla dashboard da telefoni o altri dispositivi collegati alla stessa rete:

```bash
python -m gui --host 0.0.0.0
```

Attenzione: da questi dispositivi è possibile anche confermare i pit stop.

**Configurazione Apex**

Se l'endpoint `config.js` di Apex non risponde, utilizzare:

```bash
python -m gui --apex-port [PORTA KARTODROMO]
```

[PORTA KARTODROMO] è la porta utilizzata dal kartodromo.

### Dopo la gara

Esportare i dati della gara utilizzando il pulsante **Esporta CSV** oppure:

```bash
python -m database.csv_export --db data/gara_AAAAMMGG.db
```

I file esportati vengono salvati in:

```text
data/export/gara_<id>
```

I file CSV utilizzano `;` come separatore e possono essere aperti direttamente con Excel.

Conservare:

```text
data/journal_<data>.jsonl
```

Questo file contiene la registrazione completa del feed Apex ed è utile per verificare come Apex ha segnalato giri e pit stop.

## 6. Database

L'applicazione utilizza SQLite.

Non è necessario installare un server database separato.

Un database SQLite può essere aperto con programmi come DB Browser for SQLite o DBeaver.

### Contenuto del database

In modalità live e manuale, la GUI salva giri, stint,
