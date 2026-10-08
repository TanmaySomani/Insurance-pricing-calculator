"""Regenerate all GLM figures from saved aggregate report CSVs.

Run from repository root: PYTHONPATH=src .venv/bin/python figures/gen_fig_glm.py
"""
from pathlib import Path
from insurance_pricing.plotting import plot_glm

plot_glm(Path(__file__).resolve().parents[1])
