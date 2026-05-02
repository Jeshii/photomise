import json
import shutil

from tinydb import Query, TinyDB
from tinydb.table import Table

from photomise.utilities.logging import setup_logging

logger = setup_logging()


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
        """
        Makes the JSON file at the database path readable by formatting it with indentation.

        Returns:
            bool: True if the JSON file was successfully formatted, False otherwise.
        """
        shutil.copy(self.path, f"{self.path}.bak")
        try:
            with open(self.path, "r") as file:
                data = json.load(file)

            with open(self.path, "w") as file:
                json.dump(data, file, indent=4, ensure_ascii=False)

            return True
        except json.JSONDecodeError:
            logger.error("Error: JSONDecodeError")
            shutil.copy(f"{self.path}.bak", self.path)
            return False
        except Exception as e:
            logger.error(f"Error: {e}")
            shutil.copy(f"{self.path}.bak", self.path)
            return False
