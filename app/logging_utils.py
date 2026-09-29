"""CP1 — Structured logging.

`print("user abc hỏi gì đó")` là log cho người đọc. Cloud (Railway, Render,
Cloud Run, Datadog...) đọc log bằng máy: một dòng = một JSON object thì mới
lọc/đếm/cảnh báo được. Đây là khác biệt lớn giữa localhost và production.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """CHO SẴN — thời điểm hiện tại theo ISO-8601, múi giờ UTC."""
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, level: str = "info", **fields) -> str:
    """Ghi một dòng log JSON ra stdout."""
    # 1. Gom dict tối thiểu 3 trường và gộp các trường mở rộng
    log_data = {
        "event": event,
        "level": level.lower(),
        "timestamp": utc_now_iso(),
        **fields,
    }

    # 2. Serialize thành đúng 1 dòng, giữ nguyên tiếng Việt (ensure_ascii=False), không dùng indent
    log_line = json.dumps(log_data, ensure_ascii=False)

    # 3. In ra stdout trên một dòng duy nhất
    print(log_line)

    # 4. Trả về chuỗi JSON
    return log_line