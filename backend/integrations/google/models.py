"""Strict event/mail proposal inputs; hidden recipients and attachments are not supported."""

from datetime import datetime
import re
from pydantic import Field, field_validator, model_validator
from backend.tools.registry import Inputs


class EventInput(Inputs):
    title: str = Field(min_length=1, max_length=200)
    start: str = Field(min_length=1, max_length=50)
    end: str = Field(min_length=1, max_length=50)
    description: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def times(self):
        try:
            start, end = (datetime.fromisoformat(value.replace('Z', '+00:00')) for value in (self.start, self.end))
            if not start.tzinfo or not end.tzinfo or end <= start or not self.title.strip():
                raise ValueError()
        except ValueError:
            raise ValueError('Use a nonblank title and ordered ISO date-times with timezone offsets.')
        self.start, self.end = start.isoformat(), end.isoformat()
        return self


class MailInput(Inputs):
    to: list[str] = Field(min_length=1, max_length=10)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)

    @field_validator('to')
    @classmethod
    def recipients(cls, values):
        for value in values:
            if len(value) > 254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}', value):
                raise ValueError('Use bare email addresses, without display names or header characters.')
        return list(dict.fromkeys(values))

    @field_validator('subject')
    @classmethod
    def header(cls, value):
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Use a nonblank subject without control characters.')
        return value


def resource_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        from backend.integrations.google.common import GoogleError
        raise GoogleError('Invalid Google resource identifier.', 422)
    return value
