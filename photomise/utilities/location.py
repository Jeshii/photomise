from dataclasses import dataclass


@dataclass
class Location:
    latitude: float
    longitude: float
    name: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        """Create a Location instance from a dictionary."""
        return cls(**data)

    def to_dict(self) -> dict:
        """Convert the Location instance to a dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "name": self.name,
        }
