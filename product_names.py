"""Split imported model/color names without treating wheel sizes as colors."""
import re


_COLOR_START = re.compile(
    r"(?:xanh|đen|trắng|đỏ|vàng|cam|hồng|tím|nâu|xám|bạc|dương|lá|ngọc|inox)"
    r"(?=\s|$|[-/])",
    re.IGNORECASE,
)


def split_model_color(value: str) -> tuple[str, str]:
    name = " ".join(str(value or "").split())
    # An explicit separator also supports custom color names.
    parts = re.split(r"\s+-\s+", name)
    if len(parts) > 1 and parts[-1]:
        return " - ".join(parts[:-1]), parts[-1]

    # Compact exports such as X6-18 Vàng omit the separator before the color.
    sized = re.fullmatch(r"(.+-\d+)\s+(.+)", name)
    if sized and _COLOR_START.match(sized[2]):
        return sized[1], sized[2]

    # Keep legacy X6-18-Vàng, but never split bare X6-18 or ABC-Pro models.
    model, separator, color = name.rpartition("-")
    if separator and model.strip() and _COLOR_START.match(color.strip()):
        return model.strip(), color.strip()
    return name, ""
