#!/usr/bin/env python3
"""Create a diagnostic board copy without zone fills."""

import sys

import pcbnew


board = pcbnew.LoadBoard(sys.argv[1])
for zone in list(board.Zones()):
    board.Delete(zone)
pcbnew.SaveBoard(sys.argv[2], board)
