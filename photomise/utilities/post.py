import getpass

import keyring
from InquirerPy import inquirer
from utilities import constants

from photomise.database.project import ProjectDB


def get_bluesky_user(pdb: ProjectDB) -> str:
    try:
        return pdb.get_bluesky_user()
    except TypeError:
        user = inquirer.text("Enter your Bluesky username").execute()
        pdb.set_bluesky_user(user)
        return user


def get_password_from_keyring(logger, user: str):
    logger.debug(f"Attempting to get password for {user}...")
    password = keyring.get_password(constants.BLUESKY_SERVICE_NAME, user)
    if password:
        return password

    logger.debug("Unable to get password...")
    password = getpass.getpass("Enter password: ")
    keyring.set_password(constants.BLUESKY_SERVICE_NAME, user, password)
    return password
