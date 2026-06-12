"""
setup.py — L2CS-Net Model Setup Helper
Downloads and verifies model weights for the gaze estimation backend.
"""

import os
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"
MODEL_FILE = MODELS_DIR / "L2CSNet_gaze360.pkl"

DOWNLOAD_URL = "https://drive.google.com/uc?id=18S956r4jnHtSeT8z8t3z8AoJZjVnNqPJ"

def main():
    print("=" * 60)
    print("  L2CS-Net Gaze Estimation — Model Setup")
    print("=" * 60)
    print()

    # Create models directory
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✓ Models directory: {MODELS_DIR.resolve()}")

    if MODEL_FILE.exists():
        size_mb = MODEL_FILE.stat().st_size / (1024 * 1024)
        print(f"✓ Model file found: {MODEL_FILE.name} ({size_mb:.1f} MB)")
        print()
        print("Setup complete! You can start the backend:")
        print("  uvicorn main:app --host 0.0.0.0 --port 8000")
    else:
        print()
        print("✗ Model file NOT found.")
        print()
        print("Please download the pretrained L2CS-Net model weights:")
        print()
        print(f"  1. Open this URL in your browser:")
        print(f"     {DOWNLOAD_URL}")
        print()
        print(f"  2. Or use gdown:")
        print(f"     pip install gdown")
        print(f"     gdown {DOWNLOAD_URL} -O \"{MODEL_FILE.resolve()}\"")
        print()
        print(f"  3. Save the downloaded file as:")
        print(f"     {MODEL_FILE.resolve()}")
        print()
        print("After downloading, run this script again to verify.")
        sys.exit(1)


if __name__ == "__main__":
    main()
