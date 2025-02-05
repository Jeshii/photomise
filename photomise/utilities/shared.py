from InquirerPy import inquirer


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
