# Race Engineer

Cruscotto per il live timing Apex: si collega al feed di una gara,
segue la nostra squadra e mostra nel browser tutto quello che serve
per decidere la strategia.

## Cosa fa

- Legge in diretta il feed Apex (giri, pit, bandiere, classifica) e ne
  tiene un registro come copia di sicurezza.
- Calcola passo, medie e migliori su una finestra scelta (ultimi giri,
  stint, ultimi minuti), scartando i giri sporchi.
- Tiene il conto degli stint e dei piloti, con la finestra del prossimo
  pit e gli stint previsti fino alla fine.
- Confronta il nostro passo con chi ci sta davanti e dietro, in giri di
  recupero.
- Controlla i vincoli del regolamento e segnala gli avvisi.
- Salva la gara su database, così da poterla riprendere dopo una
  chiusura o riesaminarla a freddo.

## Requisiti

Solo Python 3.10 o più recente: nessun pacchetto da installare.

## Avvio

In gara, dal vivo:

```
python -m gui --team "Nome Squadra" --drivers "Marco,Luca,Andrea,Giulia"
```

La pagina si apre su http://localhost:8765.

Su una gara simulata, senza feed:

```
python -m livetiming.simulate --out data/sim.jsonl
python -m gui --replay data/sim.jsonl --speed 60 --auto-pit \
    --team "Nome Squadra" --drivers "Marco,Luca,Andrea,Giulia"
```

Riprendere l'ultima gara interrotta:

```
python -m gui --resume
```

L'elenco completo delle opzioni (circuito, porta, database, durata,
inserimento a mano) con `python -m gui --help`.

## Prove

```
python -m unittest discover -s tests
```

## Dove sta cosa

- `livetiming/` — collegamento al feed Apex, protocollo, registro,
  classifica, simulatore.
- `core/` — modelli, logica di gara, analisi dei tempi, regolamento,
  strategia.
- `app/` — sessione di gara e sorgenti (diretta, rilettura).
- `gui/` — server e pagina del cruscotto.
- `database/` — salvataggio della gara ed esportazione CSV.
- `tests/` — prove automatiche.

Per la guida passo passo, con cosa guardare in ogni scheda, vedi
[GUIDA.md](GUIDA.md).
