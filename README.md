# python_tdb

The python_tdb was a 2012 project to create a tournament organization site and database with an automatic Elo rating system.
It was originally focused on organizing tournaments and running brackets, but I started building out the database portion
to help the various tournament cataloguing projects of the time (e.g. SSBPD) and bring all of the various ideas together.
The Python TDB (Tournament Database) was my very first attempt to build a real web application intended for other people to use.

## Config file

```
[location]
webloc: 
tiostore: tio/
content: content/
pwsalt: string
snsalt: string
pwrepetitions: 5000
superadmin: admin
```

Relevant code:
```python
config.read(dataLocation + 'conf.ini')
webloc = config.get('location', 'webloc')
tiostore = dataLocation + config.get('location', 'tiostore') # Tio files
content = dataLocation + config.get('location', 'content') # HTML-based templates
pwsalt = config.get('location', 'pwsalt')
snsalt = config.get('location', 'snsalt')
pwrepetitions = config.getint('location', 'pwrepetitions')
```

## References

SSBPD on SmashBoards: https://smashboards.com/threads/official-ssbpd-unsupported-source-code-released.318870

SSBPD source code (released after this was made, but relevant): https://github.com/FoxLisk/SSBPD

## What's Here

This copy of the codebase is untested, I just went looking for it today after noticing it wasn't online anywhere.
I'm not sure if this is the latest version or just a random snapshot. If I find a better copy, I'll update this.

The site runs as a single Python webapp2 WSGIApplication. I don't recall if I initially hosted it on nginx or Apache.
It probably isn't worth getting it running again to put together instructions. It uses a configuration file to specify
a salt and repetitions.

The database is sqlite, which performed pretty well in synthetic tests on my laptop at the time.
See dbdesign.txt (may be outdated) and dbbuildscript.

The account system uses salted pbkdf2 to hash passwords, which is no longer recommended. It has a referral system to allow
permission granting and access controls. Sessions are simple session cookies, tracked in the database and cleared out on an interval.

The UI is designed around a widget and template model. I don't know if all of the frontend code is here or not, I couldn't find more.

The bracket code is the only thing nicely separated from the rest, because it came from my former project. It reads and writes JSON.

## What TDB did

Users could browse and search tournaments with Canvas2D brackets (single/double elimination and round robin), players,
multiple games (e.g. Super Smash Bros Melee, Brawl, Street Fighter), and it fully supported doubles and teams.
A tournament organizer could upload tournaments as `.tio` files, adjust properties, and so on.

The ratings, using the Elo algorithm, were designed to be run incrementally when new tournaments were added.
