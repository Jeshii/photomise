from database.base import DatabaseManager
from geopy.distance import great_circle

from photomise.utilities.constants import SHARED_DB_PATH


class SharedDB(DatabaseManager):
    def __init__(self):
        super().__init__(SHARED_DB_PATH)
        self._locations = self.get_table("locations")
        self._filters = self.get_table("filters")

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

    def get_location(self, location_name: str) -> dict:
        return self._locations.get(self._query.name == location_name)

    def get_location_coord(self, lat: float, lon: float) -> dict:
        return self._locations.get(
            (self._query.latitude == lat) & (self._query.longitude == lon)
        )

    def upsert_location(self, params: dict) -> str:
        updated = self._locations.upsert(
            {
                "name": params["location_name"],
                "latitude": params["latitude"],
                "longitude": params["longitude"],
            },
            self._query.name == params["location_name"],
        )

        if updated:
            return params["location_name"]
        else:
            return False

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
    ):
        closest_location = None
        closest_distance = max_distance_km

        for item in self._locations.all():
            location_coords = (item["latitude"], item["longitude"])
            distance = great_circle((latitude, longitude), location_coords).kilometers

            if distance < closest_distance:
                closest_location = item["name"]
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
