from pathlib import Path
from uuid import UUID


class DocumentStorage:
    """Local-disk blob storage for raw uploaded documents.

    Files are organised as <root>/<user_id>/<document_id><ext>. The interface
    is kept minimal so an S3/MinIO adapter can replace it later.
    """

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: UUID, document_id: UUID, ext: str) -> Path:
        d = self.root / str(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{document_id}{ext}"

    def save(self, user_id: UUID, document_id: UUID, content: bytes, ext: str) -> str:
        p = self._path(user_id, document_id, ext)
        p.write_bytes(content)
        return str(p)

    def load(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def delete(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)
