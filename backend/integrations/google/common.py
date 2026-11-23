"""Fixed service definitions and safe user-facing errors."""

from backend.tools.registry import ToolError


class GoogleError(ToolError):
    pass


SERVICES = ('calendar', 'gmail', 'classroom')
SCOPE = 'https://www.googleapis.com/auth/'


def scopes_for(service, write=False, send=False, role='student'):
    if service == 'calendar':
        # Writes target primary (owned) calendar only; no calendar-management grant.
        return [SCOPE + ('calendar.events.owned' if write else 'calendar.events.owned.readonly')]
    if service == 'gmail':
        scopes = [SCOPE + 'gmail.readonly']
        if write:
            scopes.append(SCOPE + 'gmail.compose')  # Google has no drafts-only scope.
        elif send:
            scopes.append(SCOPE + 'gmail.send')
        return scopes
    if service == 'classroom':
        return [SCOPE + 'classroom.courses.readonly', SCOPE + ('classroom.coursework.students.readonly' if role == 'teacher' else 'classroom.coursework.me.readonly')]
    raise GoogleError('Unknown Google integration.', 404)
