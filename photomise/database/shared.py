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
        updated = self._filters.upsert(
            {
                "name": params["name"],
                "path": params["brightness"],
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

    def count_locations(self) -> int:
        return len(self._locations)

    def get_location(self, location_name: str) -> Location:
        return Location.from_dict(
            self._locations.get(self._query.name == location_name)
        )

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
