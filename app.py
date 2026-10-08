"""Repository entry point: python -m streamlit run app.py."""
from pathlib import Path
import sys

# Also supports a fresh checkout before a regular package installation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from insurance_pricing.dashboard import main

main(Path(__file__).resolve().parent)
