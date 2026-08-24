# vexpaer's heart — clean PCB rebuild

This branch resets the PCB layout workflow without losing the previous design.

- `Old/`: complete archived V1 design and production outputs.
- `reference/`: only the electrical/spec/library files needed for the rebuild.
- `hardware/heart_v2/`: clean workspace for the new PCB.
- `PCB_WORKFLOW.md`: the one document Codex should follow from setup to final manufacturing outputs.

The new PCB must be placement-first and human-routed. Do not use the archived PCB tracks or a global autorouter as the final layout.
