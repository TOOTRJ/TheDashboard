"""Run only isolated PostgreSQL tests after an explicit command-line opt-in."""

import argparse
import os
from pathlib import Path
import sys
import unittest

from .harness import OPT_IN


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-isolated-postgres", action="store_true", required=True,
                        help="Allow creation/removal of a uniquely owned offline local Docker container")
    args = parser.parse_args()
    if not args.allow_isolated_postgres:
        parser.error("Explicit opt-in is required")
    os.environ[OPT_IN] = "1"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    directory = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(directory), pattern="test_*.py",
                                               top_level_dir=str(directory.parents[1]))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
