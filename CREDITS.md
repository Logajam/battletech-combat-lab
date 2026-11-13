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
- **Code.** MegaMek's source code is licensed under the GNU General Public License v3. This project's "princess" bot is a
  translation of MegaMek's Princess bot (from MegaMek's source), rules the rulebooks leave open were settled by reading
  MegaMek's source (cited "MegaMek" in the code), and `megamek_bridge/` is built against MegaMek (see its README). MegaMek
  is never copied into or changed by this project.

## BattleTech

This is an unofficial fan project. It is not affiliated with, endorsed by, or licensed by Microsoft Corporation, The
Topps Company, Inc., or Catalyst Game Labs.

MechWarrior, BattleMech, 'Mech and AeroTech are registered trademarks of The Topps Company, Inc. All Rights Reserved.
Catalyst Game Labs and the Catalyst Game Labs logo are trademarks of InMediaRes Productions, LLC. The BattleTech name for
electronic games is a trademark of Microsoft Corporation. MechWarrior Copyright Microsoft Corporation; MegaMek Data was
created under Microsoft's "Game Content Usage Rules" (<https://www.xbox.com/en-US/developers/rules>).

The rules come from Catalyst Game Labs' rulebooks (the BattleTech Core Rulebook, Tactical Operations: Advanced Rules and
Advanced Units & Equipment, Interstellar Operations), cited by page in the code. The rulebook index in `rules/` holds
text from those books for the project's own private reference: it is NOT covered by this project's licence, is not
part of any download, and must never be distributed.

## Open-source libraries

The programs are built with open-source Rust libraries (MIT, Apache-2.0 and similar licences); each library, its
licence and its licence text are in [`THIRD_PARTY_LICENSES.txt`](THIRD_PARTY_LICENSES.txt) (made by
`tools/third_party_licenses.py`). The replay page loads the fonts Saira Condensed and IBM Plex from Google Fonts when it
is viewed (SIL Open Font License); they are not part of the download.
