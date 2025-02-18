import json

from tinydb import Query, TinyDB
from tinydb.table import Table


class DatabaseManager:
    def __init__(self, db_path: str):
        self.path = db_path
        self.db = TinyDB(db_path)
        self._query = Query()

    def get_table(self, table_name: str) -> Table:
        return self.db.table(table_name)

    def close(self):
        self.db.close()
        self.make_json_readable()

    def make_json_readable(self) -> bool:
        try:
            with open(self.path, "r") as file:
                data = json.load(file)

            with open(self.path, "w") as file:
                json.dump(data, file, indent=4, ensure_ascii=False)

            return True
        except json.JSONDecodeError:
            return False
