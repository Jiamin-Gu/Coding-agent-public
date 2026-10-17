"""确保无论怎样调用 pytest，仓库根目录都在导入路径上。"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
