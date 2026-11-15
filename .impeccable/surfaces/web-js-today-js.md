---
version: 1
slug: "web-js-today-js"
primary_target: "web/js/today.js"
related_targets: []
---

# Today (home) surface brief

Scope: the Today route only (`#/today`, rendered by web/js/today.js). Mode: Operate. Trial redesign; other routes keep the incumbent look until the user approves a wider prototype. Styles are scoped under `body.on-today`.

Audience and job: PCA or farmer at about 05:00, phone in a pickup cab, deciding when to leave and for which field, and whether anything blocks it. Desktop use is secondary.

## Direction contract

THESIS: Today is the shop-yard lineup board. Jobs are magnetic strips in run order, and the first is pulled out with its depart time. It replaces the dark hero-card-plus-KPI dashboard.

OWN-WORLD: white melamine board inside a brushed-aluminum frame rail on a cool gray wall. Ink-black Public Sans. Each strip has a marker-color tab: green Go, amber Caution, red Stop, gray hatch No data. Times and the primary action use marker blue, and notes use red marker. Night is a graphite board with the same marker inks. No glass, no glows, no rounded card shells.

STORY: the visitor sees what goes out first and when to leave, then what follows, what is off the board and why, and which fields carry a flag. They tap Open on map.

FIRST VIEWPORT: phone, top to bottom: the board header (date, clock, request count), a red reorder note, the enlarged lead strip with field, start time, a depart/travel/finish/margin grid, a to-scale time bar and the Open on map button, then the next strips. Desktop puts the board on the left and attention and windows on the right.

FORM: Shop Yard Lineup Board, my top-ranked grounded candidate (IMPECCABLE'S PICK, chosen by the user). Signature move: strips placed onto the board in run order, with the lead strip pulled out of the column. seed:57aed190147a0b4b

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
