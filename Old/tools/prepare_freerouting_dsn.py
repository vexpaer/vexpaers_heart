#!/usr/bin/env python3
"""Remove the solid L2 plane from a Specctra routing view.

KiCad exports every copper layer to DSN.  The Holter board reserves In1.Cu as
an uninterrupted GND plane, so exposing it to an autorouter would allow signal
traces on the reference plane.  This helper removes every complete DSN form
that directly references In1.Cu while leaving the KiCad board itself unchanged.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def strip_layer_forms(text: str, layer: str) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if layer not in line:
            output.append(line)
            index += 1
            continue

        # Each direct layer reference emitted by KiCad starts a complete DSN
        # form on its own indented line (layer, plane, keepout, or pad shape).
        depth = 0
        started = False
        while index < len(lines):
            current = lines[index]
            depth += current.count("(") - current.count(")")
            started = started or "(" in current
            index += 1
            if started and depth == 0:
                break

    result = "".join(output)
    if layer in result:
        raise ValueError(f"Failed to remove every {layer} reference")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--layer", default="In1.Cu")
    args = parser.parse_args()

    source = args.input.read_text(encoding="utf-8")
    prepared = strip_layer_forms(source, args.layer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(prepared, encoding="utf-8")

    required = ("(layer F.Cu", "(layer In2.Cu", "(layer B.Cu")
    missing = [entry for entry in required if entry not in prepared]
    if missing:
        raise ValueError(f"Prepared DSN is missing routing layers: {missing}")

    print(
        f"Prepared {args.output}: {len(source) - len(prepared)} bytes removed; "
        "routing layers are F.Cu, In2.Cu, and B.Cu"
    )


if __name__ == "__main__":
    main()
