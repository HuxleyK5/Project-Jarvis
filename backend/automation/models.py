"""Strict provider-independent plan contract. No code, expressions or result templates."""

import json
from pydantic import Field, field_validator

from backend.tools.registry import Inputs


class PlannedStep(Inputs):
    tool: str = Field(min_length=1, max_length=50)
    arguments: dict = Field(max_length=8)

    @field_validator('arguments')
    @classmethod
    def bounded(cls, value):
        if len(json.dumps(value)) > 2500:
            raise ValueError('Step arguments exceed the size limit')
        return value


class WorkflowPlan(Inputs):
    outcome: str = Field(min_length=1, max_length=300)
    steps: list[PlannedStep] = Field(min_length=1, max_length=8)

    @field_validator('outcome')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Outcome cannot be blank')
        return value
