# Archive

`bttt_removal.patch` is the commit that removed the BTTT bot (a from-scratch re-implementation of the computer opponent of Raptor007's BTTT)
from main (Daniel, 2026-11-25: "BTTT Needs to be removed from public facing builds ... remove it from the main branch so long as it can be
reinstalled later"). It holds the whole change: `bttt.rs`, its tests, the six `bttt_*` reference battles and logs, and every hook (bot lists,
`btsim --bttt`, the Lab's bot list, the credits). To put it back:

    git apply -R archive/bttt_removal.patch

then run `python tests/check_rust_reference.py` and `cargo test`. `tools/publish_public.py` and `tools/publish_web_lab.py` refuse to publish
while `engine/core/src/bttt.rs` exists, until Daniel lifts the hold. The folder is on the public copy's private paths.

**2026-11-25: BTTT is back in main** (Daniel: "We have permission to use BTTT live now."): the patch was reversed, the publish holds were lifted, BTTT may ship in public builds. The patch stays here in case it is ever pulled again.
