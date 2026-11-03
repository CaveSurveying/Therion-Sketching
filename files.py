# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Writing the tools' files."""


def write(path, data):
    """Write `data` (bytes) to `path` unless the file already holds exactly
    that, so a step that changes nothing leaves the file and its date as
    they were. True if written."""
    try:
        with open(path, 'rb') as f:
            if f.read() == data:
                return False
    except FileNotFoundError:
        pass
    with open(path, 'wb') as f:
        f.write(data)
    return True
