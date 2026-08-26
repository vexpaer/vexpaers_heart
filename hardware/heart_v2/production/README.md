# Heart V2 Rev A production package

Fabrication target: four layers, 0.8 mm, 100 x 32 mm, ENIG.  Confirm the exact
0.8 mm stackup and the 0.24 mm 50-ohm RF geometry with the selected board house
before ordering.

## Files

- `heart_v2_fab_revA.zip`: Gerber X2/job, PTH/NPTH drill and IPC-D-356 data.
- `heart_v2_release_revA.zip`: complete source, checks, fabrication and assembly
  deliverables.
- `heart_v2_bom.csv`: assembly BOM with DNP parts excluded.
- `heart_v2_bom_all.csv`: engineering BOM including DNP parts.
- `heart_v2_cpl.csv`: both-side metric placement file, DNP excluded.
- `docs/heart_v2_assembly_top.pdf`: 1:1 top assembly drawing.
- `docs/heart_v2_assembly_bottom.pdf`: 1:1 mirrored bottom assembly drawing.
- `docs/heart_v2_copper_layers.pdf`: four-page 1:1 copper review drawing.
- `docs/heart_v2_schematic.pdf`: schematic review PDF.
- `../docs/jlcpcb_pcba_order_guide.html`: detailed Chinese JLCPCB PCB+SMT ordering
  and first-board bring-up guide (open locally in a browser).

Gerber, drill and CPL outputs share the physical lower-left board corner as
their origin.  CPL positions are all positive.  Verify bottom-side rotation and
the rendered placement preview in the assembler portal before approval.

J3/J5 USB/SWD pogo contacts and TP1-TP6 test pads are bare board-contact/test
structures, not SMT parts, so they are intentionally omitted from the BOM/CPL
matching list.  The assembled board still contains their copper pads.

The board is a non-isolated research prototype.  Disconnect electrodes before
USB, and validate with an ECG simulator/patient-equivalent load before any human
connection.
