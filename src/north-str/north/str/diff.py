import difflib


def diff_strings(a: str, b: str, *, rich_colors: bool = False) -> str:
    output: list[str] = []
    matcher = difflib.SequenceMatcher(None, a, b)
    if rich_colors:
        green = "[green][reset]"
        red = "[red][reset]"
        endgreen = "[/reset][/green]"
        endred = "[/reset][/red]"
    else:
        green = "\x1b[38;5;16;48;5;2m"
        red = "\x1b[38;5;16;48;5;1m"
        endgreen = "\x1b[0m"
        endred = "\x1b[0m"

    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == "equal":
            output.append(a[a0:a1])
        elif opcode == "insert":
            output.append(f"{green}{b[b0:b1]}{endgreen}")
        elif opcode == "delete":
            output.append(f"{red}{a[a0:a1]}{endred}")
        elif opcode == "replace":
            output.append(f"{green}{b[b0:b1]}{endgreen}")
            output.append(f"{red}{a[a0:a1]}{endred}")
    return "".join(output)
