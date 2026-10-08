"""Regenerate comparison figures from committed aggregate CSVs.

Run: PYTHONPATH=src .venv/bin/python figures/gen_fig_comparison.py
"""
from pathlib import Path
from insurance_pricing.comparison_report import plot_comparison

plot_comparison(Path(__file__).resolve().parents[1])
