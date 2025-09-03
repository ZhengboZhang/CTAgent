# temp_manager.py
import os
import shutil
import time
import glob
from pathlib import Path
from typing import Union

class TempManager:
    def __init__(self, root: str = "temp", max_mb: int = 500, ttl_sec: int = 7200):
        """
        root      : 临时目录绝对或相对路径
        max_mb    : 容量警戒线（MB）
        ttl_sec   : 文件最大存活时间（秒）
        """
        self.root = Path(root).resolve()
        self.max_bytes = max_mb * 1024 * 1024
        self.ttl_sec = ttl_sec
        self.root.mkdir(exist_ok=True)

    # ------------ 对外 API ------------
    def allocate(self, suffix: str = "") -> Path:
        """返回一个可写的临时文件路径（未创建文件）"""
        ts = str(int(time.time() * 1000))
        name = f"{ts}{suffix}"
        return self.root / name

    def cleanup(self):
        """按 TTL + 容量双维度清理"""
        now = time.time()
        # 先按 TTL 清理
        for p in self.root.iterdir():
            if p.is_file() and (now - p.stat().st_mtime) > self.ttl_sec:
                p.unlink(missing_ok=True)
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)

        # 再按容量清理（最旧优先）
        total = sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())
        if total > self.max_bytes:
            files = sorted(self.root.rglob("*"), key=lambda f: f.stat().st_mtime)
            for f in files:
                if total <= self.max_bytes:
                    break
                size = f.stat().st_size if f.is_file() else 0
                try:
                    if f.is_file():
                        f.unlink()
                    else:
                        shutil.rmtree(f, ignore_errors=True)
                    total -= size
                except Exception:
                    pass

    def clear_all(self):
        """一键全清（启动时/退出时）"""
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(exist_ok=True)