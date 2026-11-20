"""Bounded assistant style settings; no arbitrary system-prompt override."""

DEFAULT_STYLE = {'tone': 'professional', 'detail': 'balanced'}
TONES = {'professional': '', 'friendly': 'Use a warm, approachable tone while remaining professional and candid.',
         'formal': 'Use a measured, formal tone with precise wording.'}
DETAILS = {'balanced': '', 'concise': 'Prefer short direct answers; expand when necessary for accuracy.',
           'detailed': 'Explain reasoning, useful examples, and relevant caveats in more detail.'}


def valid_style(value):
    return (isinstance(value, dict) and set(value) == {'tone', 'detail'}
            and isinstance(value['tone'], str) and isinstance(value['detail'], str)
            and value['tone'] in TONES and value['detail'] in DETAILS)


def style_prompt(value):
    return ' '.join(item for item in (TONES[value['tone']], DETAILS[value['detail']]) if item)
