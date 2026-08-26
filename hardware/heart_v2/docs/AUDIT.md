# Heart V2 Rev A PCB Audit

**Layout freeze:** 2026-08-26  
**Status:** manufacturing release candidate; first-board electrical, RF and
patient-equivalent-load validation is still required.

## Sign-off

| Check | Result | Evidence |
|---|---:|---|
| Schematic ERC | 0 errors, 0 warnings | `erc_final.rpt` |
| PCB DRC | 0 violations | `drc_final.rpt` |
| Connectivity | 0 unconnected pads | `drc_final.rpt` |
| Footprint errors | 0 | `drc_final.rpt` |
| Schematic/PCB electrical parity | clean | `kicad-tool pcb validate` |

The parity tool also reports 149 `footprint_symbol_field_mismatch` warnings.
They are documentation-field differences (`Description`, `Datasheet`, and
`Manufacturer`) between schematic symbols and instantiated PCB footprints;
they are not reference, value, footprint assignment, pad or net mismatches.

## Construction

- Board: 100.0 mm x 32.0 mm, 2.0 mm corner radius, 0.8 mm finished thickness.
- Stack: L1 components/signals, L2 GND reference, L3 power/signals, L4 signals.
- 167 footprints, 575 pads, 1,109 track segments and 227 through vias.
- Track widths used: 0.15 to 0.45 mm; minimum finished drill: 0.20 mm.
- 24 deliberate GND stitching vias supplement device escape/return vias.
- Top-side component density: 29.90%; bottom side is limited to three service
  footprints/contact structures (2.31%).
- Antenna keepout removes copper, tracks and vias on all four layers.
- Fabrication/pick-place datum is the physical lower-left corner.  CPL extents
  are X=3.0..97.0 mm and Y=1.0..29.5 mm, with no negative coordinates.
- J3/J5 USB/SWD pogo contacts and TP1-TP6 test pads are bare PCB contact/test
  structures; they are explicitly excluded from BOM/CPL placement matching,
  while remaining in the PCB copper and assembly drawings.

The board was rebuilt from the reference schematic and libraries.  No tracks,
vias or placement from `Old/` were reused, and no global autorouter was used.

## Routing review

Placement reads left-to-right as patient connector/protection -> ADS1294R ->
power/IMU -> STM32WB55 -> microSD/RF.  Patient input chains are aligned,
decouplers face their supply pins, MCU/ADS escapes use regular lanes, and the
long digital buses remain parallel instead of wandering between components.

L2 is a continuous GND pour except for two short, deliberate `/3V0_D` bridges:

1. a local bridge beneath U3 joining VDD drops separated by the ADS buses;
2. the J5 3 V reference feed around the USB/SWD service area.

Both alternatives were trial-routed on L3/L4 and rejected because the existing
continuous ADS/USB buses force crossings or a long perimeter detour.  The two
short L2 slots are away from RF and ECG entry traces and are bracketed by nearby
GND stitching vias.  They are controlled layout exceptions, not hidden DRC
waivers.

## Critical-net measurements

Lengths below are routed copper centerline lengths; vias are counted per KiCad
net.  Series components split some physical interfaces into multiple net names.

| Interface/net | Length | Vias | Layers/assessment |
|---|---:|---:|---|
| RF MCU -> filter (`RF_MCU`) | 3.989 mm | 0 | F.Cu |
| RF filter/match (`RF_FILTER_OUT`) | 5.456 mm | 0 | F.Cu |
| RF match -> antenna (`RF_ANT_FEED`) | 18.052 mm | 0 | F.Cu |
| USB MCU-side D- (`USB_DM`) | 2.765 mm | 0 | F.Cu |
| USB MCU-side D+ (`USB_DP`) | 2.268 mm | 0 | F.Cu |
| USB complete D- path | 16.450 mm | 2 | Pogo/ESD side plus MCU side |
| USB complete D+ path | 8.585 mm | 1 | Pogo/ESD side plus MCU side |
| SD SCK, MCU side | 14.556 mm | 2 | F.Cu/In2.Cu |
| SD MOSI, MCU side | 18.733 mm | 2 | F.Cu/B.Cu |
| SD MISO, MCU side | 13.137 mm | 2 | F.Cu/In2.Cu |
| SD CS, MCU side | 26.638 mm | 2 | F.Cu/B.Cu |
| ECG RA/LA/LL/V5 connector entry | 3.983..4.936 mm | 0 | F.Cu, aligned protection chains |
| RLD-to-RL driven path (`RL_ELEC`) | 24.224 mm | 3 | Not a measurement input pair |

The USB device-side pair is matched to 0.497 mm and is via-free.  The Pogo side
is asymmetric because the fixed `VBUS / D- / D+ / GND` contact order and the
three-pad shunt ESD footprint do not permit a natural mirrored path.  No
serpentine was added merely to equalize a 12 Mbit/s USB Full-Speed interface;
enumeration and sustained-transfer testing remain mandatory on the fixture.

The complete RF chain is 27.497 mm, top-layer and via-free over the L2 reference.
The 0.24 mm RF width must be confirmed against the exact fab stackup, and the
DNP matching capacitors must be tuned in the final enclosure.

## Assembly notes

- DNP: C10, C26, C27, C65, C66, R18 and R19.
- USB Pogo order: `VBUS / D- / D+ / GND`.
- Bottom J5 legend gives the physical left-to-right debug order.
- Do not connect USB while electrodes are attached.
- `heart_v2_bom.csv` and `heart_v2_cpl.csv` exclude DNP parts;
  `heart_v2_bom_all.csv` retains them for engineering reference.

## First-board validation

1. Inspect rails, shorts and power-source switchover before fitting electrodes.
2. Verify SWD, USB enumeration/transfer, microSD peak-current writes and RTC
   hold-up.
3. Test ECG only with a simulator or patient-equivalent load first; record input
   noise, protection leakage, lead-off behavior and RLD stability.
4. Measure RF return loss and BLE range in the final enclosure with the intended
   battery and human proximity, then freeze the pi-network population.
5. Confirm battery connector polarity, enclosure clearance and both pogo fixtures
   against the 100 x 32 mm final outline.
