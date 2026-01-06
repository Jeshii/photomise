from dataclasses import dataclass
from urllib.parse import quote, unquote


@dataclass
class Location:
    latitude: float
    longitude: float
    _name: str = ""  # private field for storing sanitized name

    @property
    def name(self) -> str:
        """Get the unsanitized name."""
        return unsanitize_text(self._name)

    @name.setter
    def name(self, value: str) -> None:
        """Set the name, ensuring it's sanitized."""
        self._name = sanitize_text(value)

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        """Create a Location instance from a dictionary."""
        # Create a copy to avoid modifying the input
        data_copy = data.copy()
        if "name" in data_copy:
            # Normalize stored names: if percent-encoded (possibly multiple times),
            # decode repeatedly to the plain text, then sanitize once so `_name`
            # stores a canonical percent-encoded representation.
            raw_name = data_copy.pop("name")
            decoded = raw_name
            try:
                while True:
                    next_decoded = unquote(decoded)
                    if next_decoded == decoded:
                        break
                    decoded = next_decoded
            except Exception:
                # If anything goes wrong with decoding, fall back to raw_name
                decoded = raw_name

            data_copy["_name"] = sanitize_text(decoded)
        return cls(**data_copy)

    def to_dict(self) -> dict:
        """Convert the Location instance to a dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "name": self._name,  # Consider whether to unsanitize here
        }


def sanitize_text(text: str = "") -> str:
    return quote(text.strip().replace(" ", "_"))


def unsanitize_text(text: str = "") -> str:
    """Reverse sanitization by URL decoding and replacing underscores with spaces."""
    return unquote(text).replace("_", " ")
