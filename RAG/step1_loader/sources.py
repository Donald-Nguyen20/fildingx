from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable, Any
import os


@dataclass
class DataScope:
    """
    Scope dữ liệu cho RAG
    """
    mode: str  # "folder" | "container"
    folder_path: Optional[str] = None
    container_name: Optional[str] = None


class DataSourceManager:
    """
    Adapter lấy file list từ Finding7.1
    """

    def __init__(self, containers: Optional[Dict[str, List[Any]]] = None):
        self.containers = containers or {}

    def list_files(
        self,
        scope: DataScope,
        exts: Optional[Iterable[str]] = None,
        max_files: Optional[int] = None
    ) -> List[str]:

        exts = {e.lower().lstrip(".") for e in exts} if exts else None
        files: List[str] = []

        if scope.mode == "folder" and scope.folder_path:
            for root, _, fnames in os.walk(scope.folder_path):
                for fn in fnames:
                    p = os.path.join(root, fn)
                    if exts:
                        if os.path.splitext(fn)[1].lower().lstrip(".") not in exts:
                            continue
                    files.append(p)
                    if max_files and len(files) >= max_files:
                        return files

        elif scope.mode == "container" and scope.container_name:
            for item in self.containers.get(scope.container_name, []):
                path = item[0] if isinstance(item, (list, tuple)) else item.get("path")
                if not path or not os.path.exists(path):
                    continue
                if exts:
                    if os.path.splitext(path)[1].lower().lstrip(".") not in exts:
                        continue
                files.append(path)
                if max_files and len(files) >= max_files:
                    return files

        return files
