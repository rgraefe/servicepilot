from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Identifier = Annotated[str, StringConstraints(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]

