# cafeandwifi
When you need to go outside, have a coffee and do some work, this is the place to find where

A map of London cafes, each assessed for how good it is to work from — Wi-Fi, sockets, toilet,
calls policy, seating capacity and coffee price — with Filters, share links and a password-protected
Curator admin area.

## Run it locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in the keys and passwords
.venv/bin/flask --app cafeandwifi run --debug --port 5050
```

The map is at http://localhost:5050 and the Curator area at http://localhost:5050/admin.

## Import the original cafes (once)

The original `cafes.db` uses the old table layout. Normalise it in place before running the site
(back the file up first):

```bash
.venv/bin/flask --app cafeandwifi import-existing
```

This follows each old map link, gives a Position to the Cafes whose links carry coordinates, turns
seat values into Seating capacity bands and prices into pence. Match the rest to a Google place in
the admin area.

## Tests

```bash
.venv/bin/python -m pytest
```
