# 🩺 Health Tracker

A personal health app for Windows that tracks **weight, water and medication** day by day.
Several people can use it on the same computer, each with their own data — and everything stays
on your computer.

## Features

- **Weight by day** — one weight per day (saving again the same day replaces it), with the change
  against the previous entry, changes over the last 7 and 30 days, and a chart of the last 90 days.
- **Water** — log each time you drink water (at the current time or a time you type), see how many
  times you drank on each day against a daily goal (8 by default), and the last 14 days at a glance.
- **Medication** — set up what you take: dose, times of day, weekdays (every day or e.g. Mon/Wed/Fri),
  a start date and an optional end date for courses like antibiotics. Each day shows a checklist of
  the doses due; tick each one once you've taken it. Doses can't be ticked for days that haven't
  happened yet, and the app reminds you on opening about today's doses that are due but not ticked.
- **Any day** — ◀ ▶, the calendar or Alt+Left / Alt+Right move between days, so you can fill in a
  day you forgot; the header shows that day's weight, water and medication at a glance.
- **Several users** — a start screen to pick who's using the app; each user has separate data and
  backups. Deleted users are moved aside, never erased.
- **Safe storage** — atomic saves (a crash never leaves a half-written file) and an automatic daily
  backup per user.

## How it's built

Python 3 with Tkinter for the interface and Pillow for the color icons; data is plain JSON files.
The user switching, storage and widgets follow the same design as the Budget Tracker project.

```
health_tracker/
  storage.py      data model (weights, water, medications, taken doses) and the JSON store
  users.py        users, each with their own data folder
  paths.py        where data lives (from source, portable, or installed)
  gui/            the window: start screen, header, dialogs, widgets, chart
  gui/tabs/       one module per tab (medications, water, weight)
tests/            unit tests (python -m unittest)
```

## Running from source

Requires Python 3 (developed with 3.14) on Windows.

```
python -m pip install -r requirements.txt
python main.py
```

[Pillow](https://pypi.org/project/pillow/) draws the color icons; without it the app still works
with plain emoji.

### Where data is stored

From source the data goes to `data/` in the project folder (the `HEALTH_TRACKER_DATA` environment
variable overrides it). Inside it:

```
users.json                  the list of users and who was used last
users/<id>/health.json      that user's weights, water, medications and taken doses
users/<id>/backups/         automatic daily backups (last 30 kept)
users/_deleted/             data of deleted users (moved here, never erased)
logs/errors.log             details of unexpected errors
```

### Tests

```
python -m unittest -v
```
