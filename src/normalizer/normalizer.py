from __future__ import annotations

import re
from typing import List


class Normalizer:
    _ws_re = re.compile(r"[ \t\f\v]+")

    def normalize_lines(self, lines: List[str]) -> List[str]:
        out: List[str] = []
        for line in lines:
            out.append(self._ws_re.sub(" ", line).strip())
        return out
