# Guida rapida: prove, gara simulata e GUI

Serve solo Python 3.10 o più recente: nessun pacchetto da installare,
nessuna connessione internet per la GUI.

Su Windows, nei comandi qui sotto `python` si può sostituire con
`.\.venv\Scripts\python.exe`. Tutti i comandi vanno lanciati dalla
cartella del progetto.

## 1. Aggiornare

```
git pull
```

## 2. Prove automatiche

```
python -m unittest discover -s tests
python main.py
```

Il primo comando deve finire con `OK` (51 prove), il secondo con
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

All'inizio compare "Gara non avviata": **Avvia gara**, scegliere pilota
e kart (proposto dal feed). A ogni PIT IN si apre da sola la finestra
del pit con il kart letto dal feed e la durata misurata: si sceglie il
nuovo pilota e si conferma. I giri arrivati nel frattempo restano in
sospeso e finiscono nello stint giusto.

## 5. Il giorno della gara

1. Leggere il nome esatto della squadra nel live timing:
   `python -m livetiming.watch --club kartandgo`
2. Avviare la GUI collegata al feed di Kart&Go:
   `python -m gui --team "NOME ESATTO" --drivers "Pilota1,Pilota2,..."`
   Il feed viene registrato in `data/journal_<data>.jsonl`: **va
   conservato**, serve a verificare come Apex segnala giri e pit.
3. Se il feed cade si continua a mano con **Giro a mano** e **PIT**.
   Senza feed fin dall'inizio: aggiungere `--manual`.
4. Se il programma si chiude: `python -m gui --resume` riprende la gara
   dal database.
5. Per vedere la pagina dai telefoni sulla stessa rete: aggiungere
   `--host 0.0.0.0` (attenzione: da lì si possono anche confermare i pit).
6. Esportare in CSV: pulsante **Esporta CSV**, oppure dopo la gara
   `python -m database.csv_export` (cartella `data/export/gara_<id>`).
   I CSV usano `;` e si aprono in Excel con un doppio clic.

## Cosa è cambiato nel codice esistente

- `database/db.py`: tolti i metodi `update_stint_*` duplicati; nuovi
  `load_race()` e `get_last_race_id()`; `RaceDatabase(..., check_same_thread=False)`
  per l'uso dalla GUI, che gira su più thread.
- `core/analytics.py`: le finestre valgono per tutta la squadra e non
  più per un solo kart (`get_laps_for_window` non prende più `kart_id`),
  lo "stint corrente" funziona anche con lo stint aperto, ci sono le
  finestre a tempo, i giri puliti e la tendenza.
- `core/strategy.py` (nuovo): finestra di pit, passo di piloti e stint,
  classifica dei kart.
- `gui/main_window.py` (vuoto) sostituito dalla GUI web in `gui/`.

## Limiti noti

Come Apex segnala giri, pit e cambi kart è ancora da verificare su un
registro reale: il simulatore è una nostra ricostruzione del formato.
Il primo journal di una gara vera è la cosa più utile da portare a casa.
