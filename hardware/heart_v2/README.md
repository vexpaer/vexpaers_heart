# heart_v2

Heart V2 Rev A is a clean, from-schematic PCB rebuild for the Holter research
prototype.  The layout is frozen as a four-layer, 0.8 mm, 100 mm x 32 mm board.
The extra 2 mm is a user-authorized service strip for separate bottom-side USB
and SWD pogo rows.

The placement and routing are deliberately scripted and reproducible.  They do
not read an archived PCB, reuse `Old/` copper, invoke Freerouting, or call a
global autorouter.

## Release status

- ERC: 0 errors, 0 warnings
- DRC: 0 violations, 0 unconnected pads, 0 footprint errors
- Schematic/PCB electrical parity: clean
- Fabrication, assembly and review outputs: `production/`
- Layout audit and first-board checks: `docs/AUDIT.md`

This is a research prototype, not a medical device.  It has no patient-side USB
isolation or defibrillation protection.  Disconnect every electrode before
connecting USB, exactly as the board silkscreen states.

## Source and regeneration

- `heart_v2.kicad_sch`, `heart_v2.kicad_pcb`, `heart_v2.kicad_pro`: KiCad 10 source
- `scripts/place_components.py`: deterministic functional placement and outline
- `scripts/route_board.py`: deterministic human-style routing, zones and stitching
- `scripts/export_release.sh`: final checks and manufacturing export
- `libraries/`: project symbols and footprints

Run the placement and routing scripts with a Python environment that provides
KiCad 10 `pcbnew`, then run the release exporter:

```bash
python3 scripts/place_components.py
python3 scripts/route_board.py
bash scripts/export_release.sh
```

Do not regenerate this board from `Old/`; that directory remains archival only.
