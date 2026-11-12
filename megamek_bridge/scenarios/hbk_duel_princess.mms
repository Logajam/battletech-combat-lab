MMSVersion: 2
name: Bridge Hunchback duel v Princess
description: MegaMek bridge - Red (our engine, --bridge Red) v Blue (MegaMek Princess), one Hunchback each, Scattered Woods.

map:
  boards:
    - file: Map Set 2/16x17 Scattered Woods.board

options:
  off:
    - simultaneous_targeting
    - simultaneous_firing
    - simultaneous_physical
    - simultaneous_deployment

factions:
  - name: Observer

  - name: Red
    bot:
      ai: PRINCESS
    units:
      - fullname: Hunchback HBK-4G
        at: [ 8, 2 ]
        facing: 3
        crew:
          name: Red Pilot
          gunnery: 4
          piloting: 5

  - name: Blue
    bot:
      ai: PRINCESS
    units:
      - fullname: Hunchback HBK-4G
        at: [ 8, 15 ]
        facing: 0
        crew:
          name: Blue Pilot
          gunnery: 4
          piloting: 5
