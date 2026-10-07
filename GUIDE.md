# Race Engineer Strategy Assistant— User Guide

This guide explains how to test the project, run a simulated race, and use the application during a real race.

Python 3.10 or newer is required. No additional packages are needed.

All commands must be run from the project directory.

On Windows, replace `python` with `.\.venv\Scripts\python.exe` (or `python`).
On Linux and WSL, use `python3` if required.

## 1. Update the project

Before testing or running a race:

```bash
git pull
```

## 2. Run the tests

Run the automated tests:

```bash
python -m unittest discover -s tests
```

The command should finish with:

```text
OK
```

You can also run the main test program:

```bash
python main.py
```

It should finish with:

```text
TEST COMPLETATO
```

`main.py` writes to `data/race_engineer.db`, which is excluded from Git.

## 3. Run a simulated race

The simulator generates a six-hour race using the same format as the Apex feed.

The simulation includes:

* 16 teams
* 14 pit stops per team
* Karts rotating between teams
* One yellow flag between 2:10 and 2:14

The simulation is deterministic, so the file does not need to be stored in Git and can be regenerated at any time.

```bash
python -m livetiming.simulate --out data/sim.jsonl
```

## 4. Run the GUI with the simulation

Start the GUI using the simulated race:

```bash
python -m gui --replay data/sim.jsonl --speed 60 --auto-pit --team "Scuderia Arcobaleno" --drivers "Marco,Dante,Massimo,Mario,Luigi,Yoshi"
```

The dashboard opens at:

```text
http://localhost:8765
```

If the browser does not open automatically, open the address manually.

With `--speed 60`, the six-hour race runs in approximately six minutes.

`--auto-pit` automatically confirms pit stops.

This mode does not write to the database.

Press `Ctrl+C` to stop the application.

### What to check

**Top bar**

Shows the main race information:

* Position
* Gap
* Lap
* Race time and remaining time
* Flag
* Feed status

The **Analysis** menu selects the analysis window: last N laps, current stint, or last N minutes. The selected window applies to the team, competitors, and graphs.

**Race**

Shows:

* Current driver and kart
* Stint duration compared with the 45-minute limit
* Last lap, average and best lap within the selected window
* Next pit and its available window
* Pace comparison with the cars ahead and behind
* Estimated recovery time and laps needed to catch the car ahead
* Stint timeline, including pit windows and planned stints

**Standings**

Shows all teams and their statistics for the selected analysis window.

**Drivers & Stints**

Shows the complete race grouped by driver, each driver's pace, and a table of stints.

Click a stint to analyse it.

In the simulation, Paolo is intentionally the slowest driver.

**Karts**

Shows the kart ranking calculated from laps recorded across all teams.

Two simulated karts are intentionally slower than the others.

**Rules & Log**

Shows rule checks, warnings, pit stops, and race events.

### Lap filtering

Average and pace calculations exclude dirty laps.

A lap is considered dirty when it is above 107% of the median lap time, for example because of a pit stop or yellow flag.

Dirty laps are displayed as triangles at the top of the graphs.

### Test the pit-stop flow manually

To test pit stops manually, remove `--auto-pit` and reduce the simulation speed:

```bash
python -m gui --replay data/sim.jsonl --speed 10 --team "Scuderia Arcobaleno" --drivers "Marco,Dante,Massimo,Mario,Luigi,Yoshi"
```

At the start, the driver selection window opens automatically.

When a **PIT IN** is detected, the pit window opens automatically. Select the next driver and confirm the stop.

The new kart and stint duration are taken from the feed when the kart leaves the pits.

Laps received while the pit is being processed remain pending and are assigned to the correct stint once the pit is completed.

## 5. Race day

A laptop with internet access is required for the live Apex feed. A phone hotspot is sufficient.

The dashboard itself works locally and does not require an internet connection.

### Before the race

1. Update the project and run the tests from Section 2.

2. Check the exact team name registered with the timing system:

```bash
python -m livetiming.watch --club "EXACT CIRCUIT NAME"
```

Press `Ctrl+C` to exit.

Use the exact name shown in the relevant column.

3. Start the GUI with the team name and all drivers:

```bash
python -m gui --team "EXACT TEAM NAME" --drivers "Driver1,Driver2,Driver3,Driver4,Driver5,Driver6" --db data/race_AAAAMMDD.db
```

The driver order does not determine the stint order. The driver is selected at every pit stop.

If the browser does not open automatically, go to:

```text
http://localhost:8765
```

The top bar should show:

```text
Live · connected
```

Once the team is found in the starting grid, the **team not connected** message disappears.

4. Select the starting driver.

The race start is determined by the feed. The starting driver is selected manually through **Select starting driver**.

This can be done before or after the race starts.

During practice and qualifying, and while the race timer is stopped on the grid, no race data is processed. At the start, the race time, lap and kart are taken from the feed.

If no starting driver has been selected, the selection window opens automatically and incoming laps remain pending until a driver is selected.

The first stint still starts from the actual race start.

If the GUI is started after the race has already begun:

* without a previous pit, the current stint starts from `0:00`;
* after a pit, it starts from the last pit exit;
* if the kart is still in the pits, the application waits for it to leave.

The banner at the top shows what the application is waiting for.

A kart can also be entered manually to start the race immediately.

Use `--no-auto-start` to disable automatic starting and return to the **Start race** button.

### During the race

**Pit stops**

At every **PIT IN**, the pit window opens automatically.

Select the next driver and confirm the stop.

The kart number does not normally need to be entered manually. The team is tracked by name and the new kart is taken from the feed when it leaves the pits.

At Kart&Go, the kart number can change during the stop, sometimes more than once.

Until the kart leaves the pits, the selected driver is shown in the banner and can still be changed.

Each driver also shows the number of completed stints and driving time, helping to choose the next driver.

**Manual kart entry**

The kart field is only needed when the feed does not provide the kart number.

If a kart is entered manually and the feed later reports a different kart, a warning is displayed. The manually entered value is never changed automatically.

**Timing warnings**

If the warning **lap times are out of sync** appears more than once, note the time.

This indicates that Apex may be updating lap times differently from the expected format.

**Feed failure**

If the live feed goes down, **Manual Lap** and **PIT** can still be used.

To run the race entirely without the feed, start the application with:

```bash
python -m gui --manual
```

**Application restart**

If the application closes, resume the race using the same database:

```bash
python -m gui --resume --db data/race_AAAAMMDD.db
```

**Access from other devices**

To access the dashboard from phones or other devices on the same network:

```bash
python -m gui --host 0.0.0.0
```

Be aware that pit stops can also be confirmed from those devices.

**Apex configuration**

If the Apex `config.js` endpoint does not respond, use:

```bash
python -m gui --apex-port [PORT NUMBER]
```

[PORT NUMBER] is the circuit port.

### After the race

Export the race data using the **Export CSV** button or:

```bash
python -m database.csv_export --db data/race_AAAAMMDD.db
```

The exported files are saved in:

```text
data/export/race_<id>
```

The CSV files use `;` as the separator and can be opened directly in Excel.

Keep:

```text
data/journal_<date>.jsonl
```

This is the complete record of the Apex feed and is useful for checking how Apex reported laps and pit stops.

## 6. Database

The application uses SQLite.

No separate database server is required.

A SQLite database can be opened with tools such as DB Browser for SQLite or DBeaver.

### Database contents

In live and manual modes, the GUI writes laps, stints, pit stops and events as they happen.

Replay mode (`--replay`) does not write to the database.

If no `--db` option is specified, the default database is:

```text
data/race_engineer.db
```

This is also the database used by `python main.py`, so it may contain test races such as `Test Race`.

For a real race, always use a separate database:

```bash
--db data/race_AAAAMMDD.db
```

Use the same database path when resuming the race or exporting the data.

### Do not open the database while the GUI is running

Opening the database with another program while the GUI is writing to it can cause:

```text
database is locked
```

The GUI will continue running, but the current lap or pit event may not be saved.

Opening the database through Windows using:

```text
\\wsl$\...
```

is especially unsafe because SQLite file locking is not reliable on that path and the database may become corrupted.

### Creating a database copy

To inspect the database while the GUI is running, create a consistent copy:

```bash
python -c "import sqlite3; sqlite3.connect('data/race_AAAAMMDD.db').backup(sqlite3.connect('data/copy.db'))"
```

The copy can then be opened safely.

From Windows, on the same laptop, it can be found at:

```text
\\wsl$\Ubuntu\<project-folder>\data\copy.db
```

For another computer, transfer the copy using a USB drive or another suitable method.

To obtain more recent data, close the copy in the program that is using it and run the backup command again.

### Without a SQLite program

The **Export CSV** function can also be used during a race.

The exported files use `;` as the separator and can be opened in Excel on any computer.

## 7. Known limitations

The application has been tested with real Apex feeds from:

* Pomposa
* Misanino
* Kart&Go

The connection, starting grid, columns, and timer format (milliseconds every 30 seconds) have been verified.

The behaviour of Apex when reporting laps, pit stops and kart changes still needs further verification because no kart was c
