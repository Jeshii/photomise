from InquirerPy import inquirer
from rich.console import Console
from spellchecker import SpellChecker


def min_max_check(value: float, min_val: float = 0.0, max_val: float = 2.0) -> float:
    if not value:
        return False
    if value < min_val:
        return False
    if value > max_val:
        return False
    return True


def make_min_max_prompt(
    message: str, default: float, min_val: float = 0.0, max_val: float = 2.0
) -> float:
    result = inquirer.text(
        message=f"{message}",
        default=str(default),
        filter=set_min_max,
        invalid_message=f"Please enter a number between {min_val} and {max_val}",
    ).execute()

    return float(result)


def set_min_max(value: float) -> float:
    value = float(value)
    if value < 0:
        return 0
    elif value > 2:
        return 2
    return value


def spellcheck(text: str) -> str:
    spell = SpellChecker()
    console = Console()
    # Clean and check spelling
    cleaned_text = "".join(char for char in text if char.isalnum() or char.isspace())
    misspelled = spell.unknown(cleaned_text.split())
    if misspelled:
        console.print("\nPossible misspelled words:")
        for word in misspelled:
            suggestions = spell.candidates(word)
            if suggestions:
                suggestion_string = {", ".join(suggestions)}
            else:
                suggestion_string = "No suggestions found"
            console.print(f"'{word}' - suggestions: {suggestion_string}")
        if inquirer.confirm("Would you like to edit the description?").execute():
            text = inquirer.text(
                message="Enter corrected description:",
                default=text,
            ).execute()
    return text


def format_file_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"
