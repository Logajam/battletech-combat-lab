# Credits and licences

## This project

**BattleTech Monte Carlo simulator and Combat Lab.** Copyright (C) 2026 Daniel (Logajam).

- **Daniel**: the project, its design and direction, the BattleTech rules calls, testing.
- **Claude** (an AI model made by Anthropic): the implementation, written with Daniel (the co-author lines in the
  project's history name each change).

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
details: [`LICENSE`](LICENSE), or <https://www.gnu.org/licenses/>.

In plain words (Daniel, 2026-11-13): anyone may use, study, change, rebuild or reverse-engineer it. What they share
that is built on it must stay under the same licence, with its source, so no one can claim it and block others from
using it. The licence covers everything this project wrote: the engine, the bots, the tools, the pages, the art data
and the documents. The material below keeps its own owners and terms.

## MegaMek

With thanks to **the MegaMek Team** (<https://megamek.org>), a non-profit group of volunteers creating free software for
the BattleTech community. This project would not exist without their work.

- **Units and boards.** Every unit file (`data/*.mtf`, `data/meks.zip`) and board (`data/*.board`, `data/maps.zip`) is
  MegaMek Data, (C) 2025 by The MegaMek Team, licensed under **Creative Commons Attribution-NonCommercial-ShareAlike
  4.0 International** (CC BY-NC-SA 4.0): [`licenses/CC-BY-NC-SA-4.0.txt`](licenses/CC-BY-NC-SA-4.0.txt), or
  <https://creativecommons.org/licenses/by-nc-sa/4.0/>. They are used unchanged, each with its own notice header. They
  may not be used for commercial purposes; because the Combat Lab download includes them, the download is
  non-commercial too.
- **Equipment tables.** `mechsim/equipment.json` and `mechsim/equipment_bv.json` (weapon and equipment stats, Battle
  Values) were built from MegaMek's equipment data and source code.
- **Availability tables** (2026-11-14): `engine/lab/web/availability.json` is MegaMek Data (the `mm-data` repository's
  `data/forcegenerator` era tables and `data/universe/factions`), reduced to a bit mask per 'Mech per era by
  `tools/make_availability.py`, following MegaMek's RAT generator (`RATGenerator.java`). Same licence as above
  (CC BY-NC-SA 4.0, non-commercial); the file carries MegaMek's notice in its `_license` field.
- **Unit images (sprites)** (2026-11-25): MegaMek's top-down unit images (35 of them, from `reference_art/megamek_sprites/`) are packed
  unchanged into `engine/lab/web/mechsprites.js` (`tools/make_mechsprites.py`) and shown as the picture on each unit's base in the 3D
  tabletop view; they ship with the Combat Lab pages. They are (C) the MegaMek Team and the unit image artists, CC BY-NC-SA 4.0 (Daniel,
  2026-11-25: "licensed as allowed to be used for non commercial purposes, which is us"): non-commercial only, ShareAlike. The file keeps
  that notice in its header. Never relicense them; any download or copy carrying the file carries this credit. Own generic pictures for
  units without one are planned (Daniel, 2026-11-25) and will replace the plain fallback figure.
- **Every stock 'Mech's own sprite** (2026-11-27): `engine/lab/web/sprites/` holds the 3,448 top-down images MegaMek's `mekset.txt` names (from https://github.com/MegaMek/mm-data, `data/images/units/meks`), unchanged, with `sprites/CREDITS.txt` (the artists named in `mekset.txt`); `spritemap.js` maps a unit's name to its file; `tools/make_mechsprites_all.py` makes both. Same licence and rules as the line below.
- **MegaMek's asset licence, CONFIRMED against its own repository (2026-11-27; this closes the question, do not reopen it).** Read from
  `github.com/MegaMek/megamek` (`LICENSE`, `LICENSE.assets`, `README.md`): game data, artwork and other non-code assets are
  non-commercial only. `LICENSE` names CC BY-NC-SA 4.0 for "all game data and assets" and `LICENSE.assets` holds that full licence text; the
  README and parts of `LICENSE` say CC BY-NC 4.0 (no ShareAlike), an inconsistency inside MegaMek's own files. We follow the stricter one,
  BY-NC-SA 4.0. Non-commercial use is allowed: this project is free, has no ads, sales or subscriptions, and so qualifies. What we must do: keep
  the credit and licence notice with every copy (done: `mechsprites.js` header, this file, `licenses/CC-BY-NC-SA-4.0.txt`), say when an image is
  changed, never relicense the images (they stay BY-NC-SA inside our GPL project), and never sell or monetise the project. MegaMek's own
  exception for monetised videos and streams of gameplay does not extend to "monetized websites, apps, or services built primarily on
  MegaMek game data". The licence does not cover trademarks: BattleTech, MechWarrior and BattleMech belong to their owners (see the
  BattleTech notice above); this project is an unofficial fan work. MegaMek has no per-file exceptions we could find for the unit images.
  So: every stock unit may use its MegaMek sprite, under these terms.
- **Code.** MegaMek's source code is licensed under the GNU General Public License v3. This project's "princess" bot is a
  translation of MegaMek's Princess bot and its "caspar" bot a translation of MegaMek's CASPAR bot (Mutual Support movement
  and deployment; `engine/core/src/caspar.rs`), both from MegaMek's source, and both deploy by a translation of MegaMek's bot
  deployment (`BotClient` / `Princess`; `engine/core/src/princess_deploy.rs`), rules the rulebooks leave open were settled by reading
  MegaMek's source (cited "MegaMek" in the code), and `megamek_bridge/` is built against MegaMek (see its README). MegaMek
  is never copied into or changed by this project.

## BTTT

**BTTT: BattleTech TableTop** by Raptor007 (Blair Sherman), <https://github.com/Raptor007/BTTT>, a fan-made computer game of tabletop BattleTech.
It has no licence, so this project copies none of its code, sounds, textures or other files. Its game and its computer opponent were studied
for ideas (how a simple one-turn bot weighs damage, cover and heat), and anything built from them is written from scratch. With thanks to the author.

## BattleTech

This is an unofficial fan project. It is not affiliated with, endorsed by, or licensed by Microsoft Corporation, The
Topps Company, Inc., or Catalyst Game Labs.

MechWarrior, BattleMech, 'Mech and AeroTech are registered trademarks of The Topps Company, Inc. All Rights Reserved.
Catalyst Game Labs and the Catalyst Game Labs logo are trademarks of InMediaRes Productions, LLC. The BattleTech name for
electronic games is a trademark of Microsoft Corporation. MechWarrior Copyright Microsoft Corporation; MegaMek Data was
created under Microsoft's "Game Content Usage Rules" (<https://www.xbox.com/en-US/developers/rules>).

The rules come from Catalyst Game Labs' rulebooks (the BattleTech Core Rulebook, Tactical Operations: Advanced Rules and
Advanced Units & Equipment, Interstellar Operations), cited by page in the code and described in the project's own words. No rulebook text is part of this project or
of any download: the project reads the books from a separate, private reference library.

## Open-source libraries

The programs are built with open-source Rust libraries (MIT, Apache-2.0 and similar licences); each library, its
licence and its licence text are in [`THIRD_PARTY_LICENSES.txt`](THIRD_PARTY_LICENSES.txt) (made by
`tools/third_party_licenses.py`). The replay page loads the fonts Saira Condensed and IBM Plex from Google Fonts when it
is viewed (SIL Open Font License); they are not part of the download.

**three.js** (MIT, Copyright 2010-2021 three.js authors, <https://threejs.org>): `engine/lab/web/three.min.js`, release r128, unchanged,
with its own licence notice in the file's first lines. It draws the 3D tabletop view of the map (`tabletop.js`) and is downloaded by the
play page only when that view is asked for. It is JavaScript the page loads, not a Rust library, so it is not in `THIRD_PARTY_LICENSES.txt`.
