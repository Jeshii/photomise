import getpass

import keyring
from keyring.errors import KeyringError
from typer import prompt

from photomise.database.project import ProjectDB
from photomise.utilities.constants import BLUESKY_SERVICE_NAME


def get_bluesky_user(pdb: ProjectDB) -> str:
    try:
        return pdb.get_bluesky_user()
    except TypeError:
        user = prompt("Enter your Bluesky username")
        pdb.set_bluesky_user(user)
        return user


def get_password_from_keyring(logger, user: str):
    logger.debug(f"Attempting to get password for {user}...")
    password = None
    try:
        password = keyring.get_password(BLUESKY_SERVICE_NAME, user)
        if password:
            logger.debug("Successfully retrieved password from keyring")
            return password
    except KeyringError as e:
        logger.debug(f"Standard keyring error: {e}")
    except Exception as e:
        logger.debug(f"Unexpected keyring error: {type(e).__name__}: {e}")

    if password:
        return password

    logger.debug("Unable to get password...")
    password = getpass.getpass("Enter password: ")
    keyring.set_password(BLUESKY_SERVICE_NAME, user, password)
    return password
