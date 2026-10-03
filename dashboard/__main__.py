"""python -m dashboard — launch the LeadGen web dashboard."""

import os
import sys

# Ensure the project root is importable regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard import main

if __name__ == '__main__':
    main()
