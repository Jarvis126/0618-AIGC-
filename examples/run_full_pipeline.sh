#!/usr/bin/env bash
set -euo pipefail

python scripts/generate_shot01.py
python scripts/generate_storyboard_api.py --shots 02 03 04 05 06 07A 07B 08A 08B 09
python scripts/stitch_storyboard.py
python scripts/qa_storyboard.py
