# Memchester Soccer finances

A small, dependency-free Python 3.12+ web application for income, expenses, balances, CSV exports, and owner-managed access.

## Run

```sh
cd /workspace/memchester-platform
python app.py
```

The server binds to loopback port 8000 by default. Open the application through your own local browser or a separately configured HTTPS deployment. First visit creates the owner account; choose the correct three-letter currency code (GBP is only a default). No real financial records or accounts are seeded.

Users sign in with email as an identifier plus an 8–32 digit PIN. The owner adds, resets, and revokes users through the access portal. All active users can view, add and export transactions. Email invitations, password recovery, bank connections, transaction editing and multi-currency accounting are not implemented. Correct an entry by adding an equal opposite transaction and a replacement, keeping the history intact.

## Data and deployment

SQLite records live in ignored `data/finance.sqlite3`; set `MEMCHESTER_DATA` to a persistent private directory to override it. Back up the database with SQLite's backup API before upgrades; retain encrypted backups separately. Sessions are in memory and expire after eight hours or server restart. PINs are salted and hashed with PBKDF2. Login attempts are limited per source IP.

For shared use, deploy behind an HTTPS reverse proxy, set `MEMCHESTER_SECURE_COOKIE=1`, and retain the default loopback binding unless a trusted deployment requires otherwise. `MEMCHESTER_HOST` and `PORT` control binding. Initialize the owner account privately before exposing the service. This built-in HTTP server is for the initial single-instance workflow; a public production service needs a hardened application server, deployment configuration, monitoring and backups. No public deployment has been created by cloud onboarding.

Run functional checks with `python -m unittest -v`. They use a temporary database and never touch club records.
