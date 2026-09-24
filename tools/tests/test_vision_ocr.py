"""The vision-OCR vote (tools/vision_ocr.py) keeps its self-check green."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import vision_ocr  # noqa: E402


def test_vote_self_check():
    vision_ocr._demo()
