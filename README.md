# Race Engineer Strategy Assistant

Assistant for Race Engineer in kart endurance race for circuits with Apex live timing: connects to a race feed, tracks our team, and displays everything needed in the browser to make strategic decisions.

## What it does

* Reads the Apex feed live (laps, pit stops, flags, standings) and keeps a local record as a backup.
* Calculates pace, averages, and best lap times over a selected window (last laps, stint, last few minutes), filtering out dirty laps.
* Tracks stints and drivers, including the next pit window and planned stints until the end of the race.
* Compares our pace with the cars ahead and behind over recovery laps.
* Checks regulatory constraints and displays warnings.
* Saves the race to a database so it can be resumed after an interruption or reviewed afterwards.

## Requirements

Python 3.10 or newer only: no additional packages need to be installed.

## Running

For a live race:

```bash
python -m gui --team "Team Name" --drivers "Marco,Luca,Andrea,Giulia"
```

The page opens at `http://localhost:8765`.

For a simulated race, without a live feed:

```bash
python -m livetiming.simulate --out data/sim.jsonl
python -m gui --replay data/sim.jsonl --speed 60 --auto-pit \
    --team "Team Name" --drivers "Marco,Luca,Andrea,Giulia"
```

To resume the last interrupted race:

```bash
python -m gui --resume
```

For the complete list of options (circuit, port, database, race duration, manual input), run:

```bash
python -m gui --help
```

## Tests

```bash
python -m unittest discover -s tests
```

## Project structure

* `livetiming/` — Apex feed connection, protocol, race record, standings, and simulator.
* `core/` — models, race logic, lap-time analysis, regulations, and strategy.
* `app/` — race session and data sources (live, replay).
* `gui/` — server and dashboard interface.
* `database/` — race storage and CSV export.
* `tests/` — automated tests.

For the step-by-step guide, including what to look at in each dashboard tab, see [GUIDE.md](GUIDE.md).
