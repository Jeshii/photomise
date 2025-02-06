from pathlib import Path

import pendulum

from ..utilities.logging import setup_logging
from .base import DatabaseManager

logging, console = setup_logging()


class ProjectDB(DatabaseManager):
    def __init__(self, project_name: str, project_path: Path):
        super().__init__(f"{project_path}/db/{project_name}.json")
        self.name = project_name
        self.path = f"{project_path}/db/{project_name}.json"
        self._events = self.get_table("events")
        self._photos = self.get_table("photos")
        self._videos = self.get_table("videos")
        self._settings = self.get_table("settings")
        self._posts = self.get_table("posts")
        self._accounts = self.get_table("accounts")

    @property
    def settings(self):
        return self._settings.all()[0] if self._settings.all() else {}

    def upsert_settings(self, settings: dict):
        return self._settings.upsert(settings, self._query.doc_id == 1)

    def get_bluesky_user(self):
        try:
            return self._accounts.get(self._query.where == "Bluesky")["user"]
        except TypeError:
            return None

    def set_bluesky_user(self, user: str):
        self._accounts.insert({"where": "Bluesky", "user": user})

    def get_events_without_bluesky_posted(self):
        events = {}
        posted_events = []
        for post in self._posts.all():
            if post["where"] == "Bluesky":
                posted_events.append(post["event"])
        for event in self._events.all():
            if event["event"] not in posted_events:
                events[event["event"]] = event
        return events

    def get_event(self, event_name: str):
        logging.info(f"[{self.name}] Getting event: {event_name}")
        return self._events.get(self._query.event == event_name)

    def get_all_events(self):
        events = {}
        for document in self._events.all():
            events[document["event"]] = document
        return events

    def set_post(self, event_name, user, platform, uri):
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

    def find_events_with_photo(self, photo_path: str) -> list:
        """Find all events containing a specific photo."""
        events_with_photo = []
        for event in self._events.all():
            if photo_path in event.get("photos", []):
                events_with_photo.append(event)
        return events_with_photo

    def remove_photo_from_event(
        self, events: list, photo_path: str, keep_idx: int
    ) -> None:
        # Remove photo from all other events
        keep_event = events[int(keep_idx) - 1]
        for event in events:
            if event["event"] != keep_event["event"]:
                photos = event.get("photos", [])
                photos.remove(photo_path)
                self._events.update(
                    {"photos": photos}, self._query.event == event["event"]
                )

    def get_photo(self, path: str):
        return self._photos.get(self._query.path == path)

    def upsert_photo(self, photo: dict):
        updated = self._photos.upsert(photo, self._query.path == photo["path"])
        return updated

    def same_event(
        self, date: pendulum, location: str, max_time_delta_in_hours: int = 8
    ):
        for item in self._events.all():
            db_date = pendulum.from_timestamp(item["date"])
            time_delta = date.diff(db_date).in_hours()

            if time_delta < max_time_delta_in_hours and location == item["location"]:
                return db_date, item["event"], True
        return date, None, False

    def is_event(self, date: pendulum.DateTime):
        return self._events.search(self._query["date"] == date.timestamp())

    def upsert_event(self, event: dict, path: str = None):
        """
        event_table.update(
                        {"photos": event.get("photos", []) + [relative_path]},
                        Event.event == event_name,
        """
        if path:
            event["photos"] = event.get("photos", []) + [path]

        updated = self._events.upsert(
            event, self._query.where("event") == event["event"]
        )
        return updated
