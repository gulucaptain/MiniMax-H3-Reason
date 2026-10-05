#!/usr/bin/env python3
"""Evaluate VDR videos through the unified submission interface."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluator.runner import main

if __name__ == "__main__":
    raise SystemExit(main(default_scenarios=["VDR"]))
