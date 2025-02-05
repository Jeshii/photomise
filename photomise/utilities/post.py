from InquirerPy import inquirer

from ..database.project import ProjectDB


def get_bluesky_user(pdb: ProjectDB) -> str:
    try:
        return pdb.get_bluesky_user()
    except TypeError:
        user = inquirer.text("Enter your Bluesky username").execute()
        pdb.set_bluesky_user(user)
        return user
