import os
from typing import List

import pendulum
from tinydb.queries import Query

from photomise.database.base import DatabaseManager
from photomise.database.shared import SharedDB
from photomise.utilities.event import Event
from photomise.utilities.location import Location
from photomise.utilities.logging import setup_logging
from photomise.utilities.photo import Photo

logger, console = setup_logging()


class ProjectDB(DatabaseManager):
    def __init__(self, project_name: str = "", project_path: str = ""):
        """
        Initialize the project database object.

        Args:
            project_name (str): Name of the project.
            project_path (Path): Path to the project.
        """
        if not project_name and not project_path:
            raise ValueError("Project name or path is required.")
        if not project_name:
            if os.path.exists(project_path):
                files = os.listdir(f"{project_path}/db")
                if len(files) == 1:
                    project_name = files[0].split(".")[0]
                else:
                    raise ValueError("Project name is required.")
            else:
                raise ValueError("Project path does not exist.")
        if not project_path:
            try:
                gdb = SharedDB()
                projects = gdb.projects
                project_path = projects[project_name]
            except ValueError:
                raise ValueError("Project path not found in global DB.")
        super().__init__(f"{project_path}/db/{project_name}.json")
        self.project_name = project_name
        self.project_path = project_path
        self.db_path = f"{project_path}/db/{project_name}.json"
        self._events = self.get_table("events")
        self._photos = self.get_table("photos")
        self._videos = self.get_table("videos")
        self._settings = self.get_table("settings")
        self._posts = self.get_table("posts")
        self._accounts = self.get_table("accounts")
        self._rankings = self.get_table("rankings")
        self._query = Query()

    # Settings table methods
    @property
    def settings(self):
        """
        Get the settings from the database.

        Returns:
            dict: Settings data.
        """
        return self._settings.all()[0] if self._settings.all() else {}

    def update_settings(self, settings: dict):
        """
        Update settings into the database.

        Args:
            settings (dict): Settings data.

        """
        return self._settings.update(settings, self._query.doc_id == 1)

    def insert_settings(self, settings: dict):
        """
        Insert settings into the database.

        Args:
            settings (dict): Settings data.

        Returns:
            bool: True if the settings were updated, False if they were inserted.
        """
        return self._settings.insert(settings)

    # Accounts table methods
    def get_bluesky_user(self) -> str | None:
        """
        Get the Bluesky user from the database.

        Returns:
            str: Bluesky username.
        """
        try:
            entry = self._accounts.get(self._query.where == "Bluesky")
            if entry:
                return entry["user"]
            else:
                return None
        except TypeError:
            return None

    def set_bluesky_user(self, user: str):
        """
        Set the Bluesky user in the database.

        Args:
            user (str): Bluesky username
        """
        self._accounts.insert({"where": "Bluesky", "user": user})

    # Events table methods
    def count_events(self):
        """
        Count the number of events in the database.

        Returns:
            int: Number of events.
        """
        return len(self._events)

    def get_event(self, event_name: str) -> Event:
        """
        Get an event from the database.

        Args:
            event_name (str): Name of the event.

        Returns:
            dict: Event data.
        """
        logger.info(f"[{self.project_name}] Getting event: {event_name}")
        return Event.from_dict(self._events.get(self._query.name == event_name))

    def get_events(self, event_names: list = []) -> list[Event]:
        """
        Get some or all events from the database.

        Args:
            event_names (list): List of event names to get. If None, get all events.

        Returns:
            dict: Dictionary of events.
        """
        events = {}
        for document in self._events.all():
            event = Event.from_dict(document)
            if not event_names or event.name in event_names:
                events[event.name] = event
        return events

    def get_events_without_bluesky_posted(self) -> list[Event]:
        """
        Get events that have not been posted to Bluesky.

        Returns:
            dict: Dictionary of events.
        """
        events = {}
        posted_events = []
        for post in self._posts.all():
            if post["where"] == "Bluesky":
                posted_events.append(post["event"])
        for document in self._events.all():
            event = Event.from_dict(document)
            if event.name not in posted_events:
                events[event.name] = event
        return events

    def same_event(
        self,
        date: pendulum.DateTime,
        location: Location,
        max_time_delta_in_hours: int = None,
    ):
        """
        Check if an event exists in the database with the same location and within a certain time delta.

        Args:
            date (pendulum.DateTime): Date of the event.
            location (str): Location of the event.
            max_time_delta_in_hours (int): Maximum time delta in hours.

        Returns:
            tuple: Date of the event, event data, and True if the event exists, False otherwise.
        """
        # get project settings for time delta and radius; fall back to shared/global DB
        settings = self.settings or {}
        if max_time_delta_in_hours is None:
            max_time_delta_in_hours = settings.get("event_time_delta_hours", 8)

        # Prefer per-project radius for portability; fall back to shared DB
        event_radius_meters = settings.get("event_radius_meters")
        if event_radius_meters is None:
            try:
                shared_db = SharedDB()
                shared_proj = shared_db.get_project(self.project_name)
                event_radius_meters = (
                    shared_proj.get("event_radius_meters") if shared_proj else 500
                )
                shared_db.close()
            except Exception:
                event_radius_meters = 500
        event_radius_km = event_radius_meters / 1000.0

        from geopy.distance import great_circle

        for item in self._events.all():
            event = Event.from_dict(item)
            # Use absolute epoch-second difference to avoid timezone/offset issues
            try:
                photo_ts = int(date.int_timestamp)
            except Exception:
                # fallback to pendulum conversion
                photo_ts = int(date.timestamp())

            try:
                event_ts = int(event.date)
            except Exception:
                event_ts = int(pendulum.from_timestamp(event.date).int_timestamp)

            time_delta_hours = abs(photo_ts - event_ts) / 3600.0
            # check temporal proximity first
            if time_delta_hours <= max_time_delta_in_hours:
                # check spatial proximity between event coordinates and provided location
                try:
                    event_coords = (event.latitude, event.longitude)
                    location_coords = (location.latitude, location.longitude)
                    distance_km = great_circle(event_coords, location_coords).kilometers
                    if distance_km <= event_radius_km:
                        return event, True
                except Exception:
                    # fallback to name matching if coordinates missing
                    if (
                        event.location == location.name
                        or event.location == location._name
                    ):
                        return event, True
        return None, False

    def is_event(self, date: pendulum.DateTime):
        """
        Check if an event exists in the database.

        Args:
            date (pendulum.DateTime): Date of the event.

        Returns:
            bool: True if the event exists, False otherwise.
        """
        return self._events.search(self._query["date"] == date.timestamp())

    def upsert_event(self, event: Event, path: str = "") -> List[int]:
        """
        Update or insert an event into the database.

        Args:
            event (dict): Event data.
            path (str): Path to a photo to add to the event.

        Returns:
            bool: True if the event was updated, False if it was inserted.
        """
        if path:
            event.photos = event.photos + [path]

        # Ensure event.date is stored as UTC epoch seconds (int)
        try:
            # If event.date is a pendulum DateTime or similar
            event_ts = int(event.date)
        except Exception:
            try:
                # If it's a float timestamp
                event_ts = int(float(event.date))
            except Exception:
                # As a last resort, leave as-is
                event_ts = event.date

        event.date = event_ts
        logger.debug(f"Upserting event: {event.name} with date {event.date}")
        existing = self._events.get(
            (self._query.name == event.name) & (self._query.date == event.date)
        )
        logger.debug(f"Found existing event: {existing}")

        updated = self._events.upsert(
            event.to_dict(),
            self._query.name == event.name,
        )
        return updated

    def remove_event(self, event: Event):
        """
        Remove an event from the database.

        Args:
            event (dict): Event data.
        """
        self._events.remove(self._query.name == event.name)

    def get_photos_without_event(self):
        """
        Get photos that are not associated with an event.

        Returns:
            list: List of photos.
        """

        all_event_photos = []
        no_event_photos = []
        for event in self._events.all():
            all_event_photos.extend(event["photos"])

        for photo in self._photos.all():
            if photo["path"] not in all_event_photos:
                print(f"Photo {photo['path']} not in any event")
                no_event_photos.append(Photo.from_dict(photo))

        return no_event_photos

    def remove_photo_from_event(self, event: Event, photo_path: str) -> None:
        """
        Remove a photo from specified event.

        Args:
            events: List of events.
            photo_path: Path to the photo.
        """

        print(f"Removing photo from {event.name}")
        photos = event.photos
        photos.remove(photo_path)
        self._events.update({"photos": event.photos}, self._query.event == event.name)

    def find_events_with_photo(self, photo_path: str) -> list[Event]:
        """
        Find all events containing a specific photo.

        Args:
            photo_path (str): Path to the photo.

        Returns:
            list: List of events containing the photo.
        """
        events_with_photo = []
        for event_dict in self._events.all():
            event = Event.from_dict(event_dict)
            if photo_path in event.photos:
                events_with_photo.append(event)
        return events_with_photo

    # Photos table methods
    def count_photos(self):
        """
        Count the number of photos in the database.

        Returns:
            int: Number of photos.
        """
        return len(self._photos)

    def get_photo(self, path: str) -> Photo | bool:
        """
        Get a photo from the database by relative path.

        Args:
            path (str): Path to the photo.

        Returns:
            Photo: Photo object.
        """

        from_db = self._photos.get(self._query.path == path)
        if not from_db:
            return Photo(
                path=path,
                quality=self.settings.get("quality", 80),
            )

        return Photo.from_dict(from_db)

    def get_photos_by_event(self, event: str) -> list[Photo]:
        """
        Get all the photos for a specific event.

        Args:
            event (str): Name of the event.

        Returns:
            list: List of photos.
        """
        photos = []
        for photo in self._photos.all():
            if event in photo.get("events", []):
                photos.append(Photo.from_dict(photo))
        return photos

    def upsert_photo(self, photo: Photo) -> list[int]:
        """
        Update or insert a photo into the database.

        Args:
            photo (Photo): Photo data.

        Returns:
            List[int]: Document IDs that were updated/inserted.
        """
        return self._photos.upsert(photo.to_dict(), self._query.path == photo.path)

    def remove_photo(self, photo: Photo):
        """
        Remove a photo from the database.

        Args:
            photo (dict): Photo data.
        """
        self._photos.remove(self._query.path == photo.path)

    # Posts table methods
    def count_posts(self):
        """
        Count the number of posts in the database.

        Returns:
            int: Number of posts.
        """
        return len(self._posts)

    def set_post(self, event_name, user, platform, uri):
        """
        Set a post in the database.

        Args:
            event_name (str): Name of the event.
            user (str): User who posted the event.
            platform (str): Platform where the event was posted.
            uri (str): URI of the post.
        """
        if uri:
            post_uri_parts = uri.split("/")
            post_url = f"https://bsky.app/profile/{user}/post/{post_uri_parts[-1]}"
        else:
            post_url = None

        self._posts.insert(
            {
                "event": event_name,
                "where": platform,
                "account": user,
                "date": pendulum.now().timestamp(),
                "link": post_url,
                "uri": uri,
            }
        )

    # Rankings table methods
    def count_rankings(self):
        """
        Count the number of rankings in the database.

        Returns:
            int: Number of rankings.
        """
        return len(self._rankings)

    def get_rankings_by_event(self, event: str):
        """
        Get rankings for a specific event.

        Args:
            event (str): Name of the event.

        Returns:
            dict: Rankings data.
        """
        rankings = self._rankings.search(self._query.event == event)
        # sort rankings by rank
        logger.debug(f"Rankings from database for {event} from DB: {rankings}")
        rankings = sorted(rankings, key=lambda x: x["rank"])
        return rankings

    def get_rank_by_photo(self, path: str):
        """
        Get the rank of a specific photo.

        Args:
            path (str): Path to the photo.

        Returns:
            int: Rank of the photo.
        """
        rankings = self._rankings.get(self._query.path == path)
        logger.debug(f"Rankings from database for {path}: {rankings}")
        return rankings.get("rank", 0) if rankings else 0

    def upsert_rankings(self, rankings: dict):
        """
        Update or insert rankings into the database.

        Args:
            rankings (dict): Rankings data.

        Returns:
            bool: True if the rankings were updated, False if they were inserted.
        """
        return self._rankings.upsert(rankings, self._query.path == rankings["path"])
