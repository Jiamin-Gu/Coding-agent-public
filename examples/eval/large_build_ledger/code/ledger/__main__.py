"""支持 ``python -m ledger``。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
