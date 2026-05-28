import json
from typing import Type, TypeVar, Any

import pydantic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def parse_dict(obj: dict[str, Any], model: Type[T]) -> T:
    """Deserialize dict into a BaseModel.

    Supports both Pydantic v1 and v2.
    """
    if hasattr(model, "model_validate"):
        # Pydantic v2
        return model.model_validate(obj)
    else:
        # Pydantic v1
        return model.parse_obj(obj)


def parse_json_list(json_str: str | bytes, model: Type[T]) -> list[T]:
    """Deserialize JSON string into a list of BaseModels.

    Supports both Pydantic v1 and v2.
    """
    return [parse_dict(item, model) for item in json.loads(json_str)]


def parse_json(json_str: str | bytes, model: Type[T]) -> T:
    """Deserialize JSON string into a BaseModel.

    Supports both Pydantic v1 and v2.
    """
    if hasattr(pydantic, "RootModel"):
        # Pydantic v2
        return model.model_validate_json(json_str)
    else:
        # Pydantic v1
        return model.parse_raw(json_str)


def stringify_basemodel(obj: BaseModel, indent: int | None = None) -> str:
    """Serialize BaseModel into a JSON string.

    Supports both Pydantic v1 and v2.
    """
    if hasattr(obj, "model_dump_json"):
        # Pydantic v2
        return obj.model_dump_json(indent=indent)
    else:
        # Pydantic v1
        return obj.json()
