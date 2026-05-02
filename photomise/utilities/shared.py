from typer import prompt


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
    while True:
        user_input = prompt(f"{message}", default=str(default))
        try:
            value = set_min_max(user_input)
        except Exception:
            print(f"Please enter a number between {min_val} and {max_val}")
            continue
        if value < min_val or value > max_val:
            print(f"Please enter a number between {min_val} and {max_val}")
            continue
        return float(value)


def set_min_max(value: float) -> float:
    value = float(value)
    if value < 0:
        return 0
    elif value > 2:
        return 2
    return value


def format_file_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"
