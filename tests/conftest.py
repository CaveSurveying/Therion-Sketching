"""Run the tests from the test cave (tests/cave), which reaches the tools
as tools.sketch2therion, as every cave does."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cave"))
collect_ignore = ["cave"]     # tools/sketch2therion there leads back to the top
