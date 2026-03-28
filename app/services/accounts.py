from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")
ACCOUNTS_FILE = DATA_DIR / "accounts.json"


@dataclass
class Account:
    name: str
    oauth_token: str
    folder_id: str
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            import hashlib
            self.id = hashlib.sha256(
                f"{self.name}:{self.folder_id}".encode()
            ).hexdigest()[:12]


class AccountManager:
    def __init__(self, path: Path = ACCOUNTS_FILE) -> None:
        self._path = path
        self._accounts: dict[str, Account] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data:
                acc = Account(**item)
                self._accounts[acc.id] = acc
        except Exception:
            logger.exception("Failed to load accounts, starting fresh")
            self._accounts = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(a) for a in self._accounts.values()]
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, name: str, oauth_token: str, folder_id: str) -> Account:
        acc = Account(name=name, oauth_token=oauth_token, folder_id=folder_id)
        self._accounts[acc.id] = acc
        self._save()
        logger.info("Account added: %s (%s)", acc.name, acc.id)
        return acc

    def remove(self, account_id: str) -> bool:
        if account_id in self._accounts:
            del self._accounts[account_id]
            self._save()
            return True
        return False

    def get(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    def list_all(self) -> list[Account]:
        return list(self._accounts.values())

    def __iter__(self) -> Iterator[Account]:
        return iter(self._accounts.values())

    def __len__(self) -> int:
        return len(self._accounts)
