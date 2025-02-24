import os
from typing import List

import pendulum
from tinydb.queries import Query
from tinydb.table import Document

from photomise.database.base import DatabaseManager
from photomise.database.shared import SharedDB
from photomise.utilities.event import Event
from photomise.utilities.location import Location
from photomise.utilities.logging import setup_logging
from photomise.utilities.photo import Photo

logging, console = setup_logging()


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

    def upsert_settings(self, settings: dict):
        """
        Update or insert settings into the database.

        Args:
            settings (dict): Settings data.

        Returns:
            bool: True if the settings were updated, False if they were inserted.
        """
        return self._settings.upsert(settings, self._query.doc_id == 1)

    # Accounts table methods
    def get_bluesky_user(self) -> Document | List[Document] | None:
        """
        Get the Bluesky user from the database.

        Returns:
            str: Bluesky username.
        """
        try:
            return self._accounts.get(self._query.where == "Bluesky")
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
        logging.info(f"[{self.project_name}] Getting event: {event_name}")
        return Event.from_dict(self._events.get(self._query.name == event_name))

    def get_events(self, event_names: list = []):
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

    def get_events_without_bluesky_posted(self):
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
        for event in self._events.all():
            if event["event"] not in posted_events:
                events[event["event"]] = event
        return events

    def same_event(
        self,
        date: pendulum.DateTime,
        location: Location,
        max_time_delta_in_hours: int = 8,
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
        for item in self._events.all():
            event = Event.from_dict(item)
            db_date = pendulum.from_timestamp(event.date)
            time_delta = date.diff(db_date).in_hours()

            if time_delta < max_time_delta_in_hours and (
                event.location == location.name or event.location == location._name
            ):
                return event, True
        return date, False

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

        updated = self._events.upsert(event.to_dict(), self._query.event == event.name)
        return updated

    ### NOT WORKING when called from handle_duplicate_events()
    def remove_photo_from_event(
        self, events: list[Event], photo_path: str, keep_idx: int = 0
    ) -> None:
        """
        Remove a photo from all events except the one specified.

        Args:
            events (list): List of events.
            photo_path (str): Path to the photo.
            keep_idx (int): Index of the event to keep the photo in. Will remove the photo from all events if 0.
        """
        if keep_idx:
            keep_event = events[int(keep_idx) - 1]
        else:
            keep_event = Event()
        print("Keep event:", keep_event)
        for event in events:
            if event.name != keep_event.name:
                print(f"Removing photo from {event.name}")
                photos = event.photos
                photos.remove(photo_path)
                self._events.update(
                    {"photos": event.photos}, self._query.event == event.name
                )

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

    def get_photos_by_event(self, event: str):
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
                photos.append(photo)
        return photos

    def upsert_photo(self, photo: Photo) -> List[int]:
        """
        Update or insert a photo into the database.

        Args:
            photo (dict): Photo data.

        Returns:
            List[int]: Document IDs that were updated/inserted.
        """
        return self._photos.upsert(photo.to_dict(), self._query.path == photo.path)

    def remove_photo(self, photo: dict):
        """
        Remove a photo from the database.

        Args:
            photo (dict): Photo data.
        """
        self._photos.remove(self._query.path == photo["path"])

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
        logging.debug(f"Rankings from database for {event} from DB: {rankings}")
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
        logging.debug(f"Rankings from database for {path}: {rankings}")
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
