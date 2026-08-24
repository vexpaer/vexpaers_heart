#!/usr/bin/env python3
"""Run KiCad sign-off checks and export review/manufacturing deliverables."""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "pdf"
DOCS = ROOT / "docs"
PRODUCTION = ROOT / "production"


@dataclass(frozen=True)
class Target:
    slug: str
    directory: Path
    stem: str
    copper: tuple[str, ...]
    bom_source: Path

    @property
    def schematic(self) -> Path:
        return self.directory / f"{self.stem}.kicad_sch"

    @property
    def board(self) -> Path:
        return self.directory / f"{self.stem}.kicad_pcb"


TARGETS = (
    Target(
        "main_board",
        ROOT / "hardware" / "holter_v1",
        "holter_v1",
        ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"),
        DOCS / "bom_source.csv",
    ),
    Target(
        "usb_pogo_dock",
        ROOT / "hardware" / "usb_pogo_dock",
        "usb_pogo_dock",
        ("F.Cu", "B.Cu"),
        DOCS / "dock_bom_source.csv",
    ),
)


def natural_key(text: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text))


def find_kicad_cli() -> str:
    configured = os.environ.get("KICAD_CLI")
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return str(path)
        raise SystemExit(f"KICAD_CLI does not point to a file: {path}")
    found = shutil.which("kicad-cli")
    if found:
        return found
    raise SystemExit("kicad-cli was not found; install KiCad 10 or set KICAD_CLI")


KICAD = find_kicad_cli()


def run(*args: object) -> None:
    command = [str(item) for item in args]
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def assert_signoff_report(path: Path, *, schematic: bool) -> None:
    report = path.read_text(encoding="utf-8")
    if schematic:
        expected = "ERC messages: 0  Errors 0  Warnings 0"
        if expected not in report:
            raise SystemExit(f"ERC is not clean: {path.relative_to(ROOT)}")
        return
    required = ("Found 0 DRC violations", "Found 0 unconnected pads", "Found 0 Footprint errors")
    missing = [text for text in required if text not in report]
    if missing:
        raise SystemExit(f"PCB sign-off is not clean ({', '.join(missing)}): {path.relative_to(ROOT)}")


def write_grouped_bom(target: Target, output: Path) -> None:
    rows = list(csv.DictReader(target.bom_source.open(encoding="utf-8-sig")))
    fitted = [row for row in rows if not row["DNP"]]
    missing = [
        row["Reference"]
        for row in fitted
        if not row["Manufacturer Part Number"]
    ]
    if missing:
        raise SystemExit(f"Fitted BOM rows without an MPN in {target.bom_source.name}: {', '.join(missing)}")

    groups: dict[tuple[str, str, str, str], list[str]] = {}
    for row in fitted:
        key = (
            row["Value"],
            row["Footprint"].split(":")[-1],
            row["Manufacturer"],
            row["Manufacturer Part Number"],
        )
        groups.setdefault(key, []).append(row["Reference"])

    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "Comment",
                "Designator",
                "Footprint",
                "LCSC Part #",
                "Manufacturer Part Number",
                "Manufacturer",
                "Quantity",
            ]
        )
        for key, references in sorted(groups.items(), key=lambda item: natural_key(min(item[1], key=natural_key))):
            value, footprint, manufacturer, mpn = key
            references.sort(key=natural_key)
            writer.writerow([value, ",".join(references), footprint, "", mpn, manufacturer, len(references)])


def fitted_references(target: Target) -> set[str]:
    with target.bom_source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["Reference"] for row in rows if not row["DNP"]}


def transform_position_file(source: Path, output: Path, allowed_references: set[str]) -> None:
    with source.open(newline="", encoding="utf-8-sig") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["Ref"] in allowed_references
        ]
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in sorted(rows, key=lambda item: natural_key(item["Ref"])):
            layer = "Top" if row["Side"].lower() == "top" else "Bottom"
            # KiCad's CSV uses a Cartesian Y axis, so board locations below
            # the top-left origin are negative.  JLC-style CPL files expect
            # positive board coordinates.  Normalize rotations at the same
            # time so no assembler has to interpret negative angles.
            pos_y = -float(row["PosY"])
            rotation = float(row["Rot"]) % 360.0
            writer.writerow(
                [
                    row["Ref"],
                    f"{float(row['PosX']):.6f}mm",
                    f"{pos_y:.6f}mm",
                    layer,
                    f"{rotation:.6f}",
                ]
            )


def zip_fabrication_files(source_dir: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.iterdir()):
            if path.is_file() and path != output:
                archive.write(path, path.name)


def export_target(target: Target) -> None:
    output = PRODUCTION / target.slug
    gerber = output / "gerber_drill"
    if output.exists():
        shutil.rmtree(output)
    gerber.mkdir(parents=True)
    PDF.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    erc = DOCS / f"{target.stem}_erc.rpt"
    drc = DOCS / f"{target.stem}_drc.rpt"
    run(KICAD, "sch", "erc", "--exit-code-violations", "--output", erc, target.schematic)
    run(KICAD, "pcb", "drc", "--exit-code-violations", "--output", drc, target.board)
    assert_signoff_report(erc, schematic=True)
    assert_signoff_report(drc, schematic=False)
    shutil.copy2(erc, output / erc.name)
    shutil.copy2(drc, output / drc.name)

    run(KICAD, "sch", "export", "pdf", "--output", PDF / f"{target.stem}_schematic.pdf", target.schematic)
    run(
        KICAD,
        "pcb",
        "export",
        "pdf",
        "--mode-multipage",
        "--black-and-white",
        "--scale",
        "0",
        "--check-zones",
        "--layers",
        ",".join(target.copper),
        "--common-layers",
        "Edge.Cuts",
        "--output",
        PDF / f"{target.stem}_pcb_layers.pdf",
        target.board,
    )
    run(
        KICAD,
        "pcb",
        "export",
        "pdf",
        "--mode-single",
        "--black-and-white",
        "--scale",
        "0",
        "--sketch-pads-on-fab-layers",
        "--crossout-DNP-footprints-on-fab-layers",
        "--layers",
        "F.Fab,F.Silkscreen,Edge.Cuts",
        "--output",
        PDF / f"{target.stem}_assembly_top.pdf",
        target.board,
    )
    run(
        KICAD,
        "pcb",
        "export",
        "pdf",
        "--mode-single",
        "--mirror",
        "--black-and-white",
        "--scale",
        "0",
        "--sketch-pads-on-fab-layers",
        "--crossout-DNP-footprints-on-fab-layers",
        "--layers",
        "B.Fab,B.Silkscreen,Edge.Cuts",
        "--output",
        PDF / f"{target.stem}_assembly_bottom.pdf",
        target.board,
    )

    gerber_layers = (*target.copper, "F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts")
    run(
        KICAD,
        "pcb",
        "export",
        "gerbers",
        "--check-zones",
        "--layers",
        ",".join(gerber_layers),
        "--output",
        gerber,
        target.board,
    )
    run(
        KICAD,
        "pcb",
        "export",
        "drill",
        "--format",
        "excellon",
        "--excellon-units",
        "mm",
        "--excellon-separate-th",
        "--generate-map",
        "--map-format",
        "pdf",
        "--generate-report",
        "--report-path",
        gerber / f"{target.stem}-drill-report.txt",
        "--output",
        gerber,
        target.board,
    )

    raw_position = output / f"{target.stem}-kicad-position.csv"
    run(
        KICAD,
        "pcb",
        "export",
        "pos",
        "--format",
        "csv",
        "--units",
        "mm",
        "--side",
        "both",
        "--smd-only",
        "--exclude-dnp",
        "--output",
        raw_position,
        target.board,
    )
    transform_position_file(
        raw_position,
        output / f"{target.stem}-cpl.csv",
        fitted_references(target),
    )
    raw_position.unlink()
    write_grouped_bom(target, output / f"{target.stem}-bom.csv")
    shutil.copy2(target.bom_source, output / f"{target.stem}-bom-source.csv")
    shutil.copy2(ROOT / "production" / "README.md", output / "manufacturing-notes.md")
    zip_fabrication_files(gerber, output / f"{target.stem}-fabrication.zip")


def main() -> None:
    for target in TARGETS:
        export_target(target)
    print("Release exports completed; all ERC/DRC/unconnected checks passed.")


if __name__ == "__main__":
    main()
