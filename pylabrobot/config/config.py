import logging
from dataclasses import dataclass, field
from pathlib import Path
<<<<<<< HEAD
=======
from typing import Optional
>>>>>>> upstream/main

LOG_FROM_STRING = {
  "DEBUG": logging.DEBUG,
  "INFO": logging.INFO,
  "WARNING": logging.WARNING,
  "ERROR": logging.ERROR,
  "CRITICAL": logging.CRITICAL,
}

LOG_TO_STRING = {v: k for k, v in LOG_FROM_STRING.items()}


@dataclass
class Config:
<<<<<<< HEAD
  """The configuration object for the application."""
=======
  """The configuration object for PyLabRobot."""
>>>>>>> upstream/main

  @dataclass
  class Logging:
    """The logging configuration."""

    level: int = logging.INFO
<<<<<<< HEAD
    log_dir: Path = Path(".")
=======
    log_dir: Optional[Path] = None
>>>>>>> upstream/main

  logging: Logging = field(default_factory=Logging)

  @classmethod
  def from_dict(cls, d: dict) -> "Config":
<<<<<<< HEAD
    """Create a Config object from a dictionary."""
    return cls(
      logging=cls.Logging(
        level=LOG_FROM_STRING[d["logging"]["level"]],
        log_dir=Path(d["logging"]["log_dir"]),
=======
    return cls(
      logging=cls.Logging(
        level=LOG_FROM_STRING[d["logging"]["level"]],
        log_dir=Path(d["logging"]["log_dir"]) if "log_dir" in d["logging"] else None,
>>>>>>> upstream/main
      )
    )

  @property
  def as_dict(self) -> dict:
<<<<<<< HEAD
    """Convert the Config object to a dictionary."""
    return {
      "logging": {
        "level": LOG_TO_STRING[self.logging.level],
        "log_dir": str(self.logging.log_dir),
=======
    return {
      "logging": {
        "level": LOG_TO_STRING[self.logging.level],
        "log_dir": str(self.logging.log_dir) if self.logging.log_dir is not None else None,
>>>>>>> upstream/main
      }
    }
