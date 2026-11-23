"""Risk is assigned by code, never by model-generated plan fields."""

from backend.tools.registry import ToolError

LOW_RISK = {'system_info', 'list_directory', 'search_files'}


def classify(registry, name, arguments, automatic):
    try:
        normalized = registry.validate(name, arguments)
    except ToolError as exc:
        return 'blocked', None, str(exc)
    category = 'automatic' if name in LOW_RISK and name in automatic else 'confirmation_required'
    return category, normalized, None
