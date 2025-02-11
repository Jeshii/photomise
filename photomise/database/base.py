import json
from pathlib import Path

from tinydb import Query, TinyDB


class DatabaseManager:
    def __init__(self, db_path: Path):
        self.path = db_path
        self.db = TinyDB(db_path)
        self._query = Query()

    def get_table(self, table_name: str):
        return self.db.table(table_name)

    def close(self):
        self.db.close()
        self.make_json_readable()

    def make_json_readable(self) -> str:
        with open(self.path, "r") as file:
            data = json.load(file)

        with open(self.path, "w") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
