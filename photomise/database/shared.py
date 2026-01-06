from geopy.distance import great_circle

from photomise.database.base import DatabaseManager
from photomise.utilities.constants import SHARED_DB_PATH
from photomise.utilities.location import Location
from photomise.utilities.logging import setup_logging

logger, console = setup_logging()


class SharedDB(DatabaseManager):
    def __init__(self):
        super().__init__(SHARED_DB_PATH)
        self._locations = self.get_table("locations")
        self._filters = self.get_table("filters")
        self._projects = self.get_table("projects")

    @property
    def projects(self):
        config = {}
        for v in self.get_table("projects").all():
            logger.debug(f"Project: {v}")
            config[v["name"]] = v["path"]
        if not config:
            raise ValueError(
                "No projects found in global database - please run photomise init."
            )
        return config

    def get_items(self, table) -> dict:
        items = {}
        for item in table.all():
            name = item.get("name")
            if name:
                items[name] = name
        return items

    def get_filter(self, filter_name: str) -> dict:
        filter = self._filters.get(self._query.name == filter_name)
        return filter

    def count_filters(self) -> int:
        return len(self._filters)

    def get_filters_all(self) -> dict:
        return self._filters.all()

    def upsert_filter(self, params: dict) -> str:
        updated = self._filters.upsert(
            {
                "name": params["name"],
                "brightness": params["brightness"],
                "contrast": params["contrast"],
                "color": params["color"],
                "sharpness": params["sharpness"],
            },
            self._query.name == params["name"],
        )

        if updated:
            return params["name"]
        else:
            return False

    def rename_filter(self, old_name: str, new_name: str) -> str:
        updated = self._filters.update(
            {"name": new_name},
            self._query.name == old_name,
        )
        if updated:
            return new_name
        else:
            return False

    def upsert_project(self, params: dict) -> str:
        # Only store minimal project info in the shared DB (name and path).
        record = {"name": params.get("name"), "path": params.get("path")}
        updated = self._projects.upsert(record, self._query.name == record["name"])

        if not updated:
            return False

        # If extra project-specific settings were provided (e.g. radius/time-delta),
        # they should live in the per-project DB for portability. Return the
        # project name and let callers optionally run migration to move the
        # additional keys into the project DB.
        return record["name"]

    def migrate_project_settings(self, project_name: str, params: dict):
        """Move project-specific settings from a params dict into the per-project DB.

        This helper will open the project DB (if path available in shared DB) and
        update the project's settings with any keys other than name/path.
        """
        # Determine project path from shared table
        project_entry = self._projects.get(self._query.name == project_name)
        if not project_entry:
            raise ValueError("Project not found in shared DB")

        project_path = project_entry.get("path")
        # Lazy import to avoid circular imports at module load
        from photomise.utilities.project import get_project_db

        pdb = get_project_db(project_name, project_path)
        project_settings = pdb.settings or {}
        # Copy any keys other than name/path into project settings
        for k, v in params.items():
            if k in ("name", "path"):
                continue
            project_settings[k] = v

        pdb.update_settings(project_settings)
        pdb.close()

    def count_locations(self) -> int:
        return len(self._locations)

    def get_location(self, location_name: str) -> Location:
        return Location.from_dict(
            self._locations.get(self._query.name == location_name)
        )

    def get_project(self, project_name: str) -> dict | None:
        """Return the full project record from the shared projects table."""
        return self._projects.get(self._query.name == project_name)

    def upsert_location(self, location: Location) -> str:
        return self._locations.upsert(
            location.to_dict(), self._query.name == location.name
        )

    def get_filter_from_values(self, params: dict) -> str:
        for filter in self._filters.all():
            if (
                filter.get("brightness") == params.get("brightness")
                and filter.get("contrast") == params.get("contrast")
                and filter.get("color") == params.get("color")
                and filter.get("sharpness") == params.get("sharpness")
            ):
                return filter.get("name", "None")
        return "None"

    def find_location(
        self, latitude: float, longitude: float, max_distance_km: float = 0.5
    ) -> Location:
        closest_location = None
        closest_distance = max_distance_km

        for item in self._locations.all():
            location_coords = (item["latitude"], item["longitude"])
            distance = great_circle((latitude, longitude), location_coords).kilometers

            if distance < closest_distance:
                closest_location = Location.from_dict(item)
                closest_distance = distance

        return closest_location

    def is_location(self, lat, lon):
        result = self._locations.search(
            (self._query.latitude == lat) & (self._query.longitude == lon)
        )
        return len(result) > 0

    def upsert_event(self, event: dict):
        """
        Update or insert an event into the database.

        event_name, relative_path, date, location, photos
        """
        updated = self._events.upsert(
            event, self._query.where("event") == event["event"]
        )
        return updated

    def delete_filter(self, filter_name: str):
        self._filters.remove(self._query.name == filter_name)
        return True
