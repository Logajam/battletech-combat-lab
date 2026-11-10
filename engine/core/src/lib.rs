//! BattleTech Monte Carlo engine - a step-for-step translation of the Python (INTEGRATION__RUST_PORT.md).
//! One module per Python module, the same name (the INTEGRATION__ prefix dropped).
pub mod pyfmt;
pub mod hex_geometry;
pub mod board_parser;
pub mod terrain_rules;
pub mod los;
pub mod equipment;
pub mod config;
pub mod battle;
pub mod mech_state;
pub mod mech_json;
pub mod damage_resolution;
pub mod mtf_parser;
pub mod pathfinder;
