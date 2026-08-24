# Holter V1 hardware release audit

Generated 2026-08-24 from the signed-off KiCad board.

## Release gates

- Main schematic: ERC 0 errors / 0 warnings.
- Main PCB: DRC 0 violations, 0 unconnected pads, 0 footprint errors.
- Vias: 253; all plated through, F.Cu–B.Cu, 0.45/0.20 mm; no blind, buried, or microvias.
- BOM: 159 source rows, 152 fitted and 7 DNP; every fitted row has a manufacturer part number.
- PCB footprint values match the BOM source; the pin/net audit has no electrical mismatches.
- Expected mechanical-only extra pads: J1-MP, J2-MP.

## Physical and layout checks

- Nominal outline: 100.00 × 30.00 mm (Edge.Cuts bounding box including stroke: 100.05 × 30.05 mm); board thickness 0.8 mm, four copper layers.
- Placement: 165 footprints on top; bottom only J3, J5; every footprint has a courtyard.
- In1.Cu has no signal tracks and contains the solid GND plane (normal pad/via antipads still apply).
- Antenna rule-area keepout is present on all four copper layers and measures 5.1 × 10.0 mm; pours and vias are forbidden there while the antenna feed is allowed.
- RF, HSE, LSE, and STM32 SMPS critical nets are front-layer-only and via-free.

## Routed-net measurements

| Net | Copper length | Vias | Layers | Widths |
|---|---:|---:|---|---|
| `USB_DM` | 39.69 mm | 3 | B.Cu, F.Cu, In2.Cu | 0.15 mm |
| `USB_DM_POGO` | 11.02 mm | 1 | B.Cu, F.Cu | 0.15 mm |
| `USB_DP` | 47.67 mm | 6 | B.Cu, F.Cu, In2.Cu | 0.15 mm |
| `USB_DP_POGO` | 11.24 mm | 2 | B.Cu, F.Cu, In2.Cu | 0.15 mm |
| `SD_SCK_MCU` | 33.18 mm | 3 | B.Cu, F.Cu, In2.Cu | 0.10 mm |
| `SD_MISO_MCU` | 36.64 mm | 3 | B.Cu, F.Cu, In2.Cu | 0.10 mm |
| `SD_MOSI_MCU` | 48.40 mm | 4 | F.Cu, In2.Cu | 0.15 mm |
| `SD_CS_MCU` | 38.01 mm | 5 | B.Cu, F.Cu, In2.Cu | 0.10 mm, 0.15 mm |
| `RF_MCU` | 1.91 mm | 0 | F.Cu | 0.10 mm, 0.18 mm |
| `RF_FILTER_OUT` | 52.91 mm | 0 | F.Cu | 0.18 mm |
| `RF_ANT_FEED` | 4.24 mm | 0 | F.Cu | 0.18 mm |
| `HSE_IN` | 12.29 mm | 0 | F.Cu | 0.10 mm, 0.12 mm |
| `HSE_OUT` | 5.67 mm | 0 | F.Cu | 0.10 mm, 0.12 mm |
| `LSE_IN` | 9.60 mm | 0 | F.Cu | 0.10 mm, 0.12 mm |
| `LSE_OUT` | 8.09 mm | 0 | F.Cu | 0.12 mm |
| `SMPS_IN` | 4.31 mm | 0 | F.Cu | 0.10 mm, 0.25 mm |
| `SMPS_SW` | 2.60 mm | 0 | F.Cu | 0.10 mm, 0.25 mm |
| `SMPS_FB` | 5.39 mm | 0 | F.Cu | 0.10 mm, 0.20 mm, 0.25 mm |

## Interface assessment

- USB routed endpoint paths (excluding ESD branches and the two 22 Ω resistor bodies): D− 48.39 mm, D+ 56.91 mm; length difference 8.52 mm. FR-4 propagation gives an estimated 50–60 ps skew. This release is for USB 2.0 Full-Speed (12 Mbit/s) only, not High-Speed; verify the selected stackup and USB behavior on the first article.
- The USB routes are not a tightly coupled controlled-impedance pair and use several vias. This is accepted for the Full-Speed prototype only and remains a first-article validation item.
- microSD MCU-side routed lengths are SCK 33.18 mm, MISO 36.64 mm, MOSI 48.40 mm, and CS 38.01 mm. Start first-board firmware at 4 MHz SPI and increase only after validation; 12 MHz is the initial recommended ceiling.
- The 2.4 GHz feed is top-layer and via-free over the In1 ground reference. Its 0.18 mm line width is not a universal 50 Ω value: the PCB vendor must calculate/confirm impedance against the actual 0.8 mm four-layer stackup, and the assembled unit requires VNA/closed-enclosure matching validation.

## ECG/RLD/WCT review

- CH1 is LA−RA, CH2 is LL−RA, and CH3 is V5−WCT; CH4 is reserved with test points. The PCB pin map matches the schematic audit CSV.
- RA/LA/LL/V5 each use two 47.5 kΩ series resistors with C0G filtering and low-leakage clamps; RLD uses 2 × 162 kΩ series limiting.
- RLDOUT/RLDINV compensation is 1 MΩ in parallel with 1.5 nF; WCT is routed to CH3N with 100 pF to ground.
- These checks establish schematic/PCB consistency only. Before any human connection, validate on an ECG simulator and patient-equivalent load: input leakage/bias, RLD stability, recovery after ESD, noise, lead-off behavior, and all relevant safety limits.

## First-article items that remain open

- RF return loss, π-network values, BLE range in the final enclosure and near the body.
- USB Full-Speed eye/function, microSD write peaks and SPI margin, RTC hold-up time, regulator temperatures, and power-path reverse-current behavior.
- Battery connector polarity, protected-pack thresholds, enclosure tolerances, Pogo alignment, and mechanical USB/electrode interlock.
- The design is a research prototype, not an IEC 60601-qualified medical device and not suitable for diagnosis or clinical decisions.
