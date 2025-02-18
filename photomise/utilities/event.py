from dataclasses import dataclass


@dataclass
class Event:
    name: str = ""
    date: float = (0,)
    latitude: float = 0.0
    longitude: float = 0.0
    location: str = ""
    photos: list[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Create an Event instance from a dictionary."""
        return cls(**data)

    def to_dict(self) -> dict:
        """Convert the Event instance to a dictionary."""
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "date": self.date,
            "location": self.location,
            "photos": self.photos,
        }
