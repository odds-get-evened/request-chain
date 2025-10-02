from pathlib import Path
from typing import Any

from tinydb import TinyDB, where
from tinydb.table import Table

KEY_PRIV_KEY = 'private_key'
KEY_SIG = 'signature'
KEY_TS = 'timestamp'
KEY_CUR_KEY = 'current_key'

TBL_IDENTS = 'idents'
TBL_SETTINGS = 'settings'


class TinyDBPersisted:
    _db: TinyDB = None

    @classmethod
    def initialize(cls, db_path: Path):
        if cls._db is None:
            db_path.parent.mkdir(parents=True, exist_ok=True)

            cls._db = TinyDB(db_path)
            print(f'db initialized from path {str(db_path)}')

    @staticmethod
    def db():
        if TinyDBPersisted._db is None:
            raise Exception(f"failed to initialize the database.")

        return TinyDBPersisted._db

    @staticmethod
    def close():
        if TinyDBPersisted._db:
            print(f"database closing")
            TinyDBPersisted._db.close()
            TinyDBPersisted._db = None
