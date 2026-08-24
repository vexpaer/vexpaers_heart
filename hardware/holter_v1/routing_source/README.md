# Routing source

`holter_v1-freerouted-input.kicad_pcb` is the frozen Freerouting intermediate
used by `tools/finish_main_routes.py`. It is committed only to make the final
manual routing stage reproducible.

Do **not** send this intermediate board to a manufacturer. It does not contain
the final PA10 microSD-CS/SD-clock completion and its imported layer-changing
drills may still be labelled as buried vias. The signed-off fabrication source
is `../holter_v1.kicad_pcb`; the finishing script converts every final drill to
a 0.45/0.20 mm ordinary plated through-via before saving.
