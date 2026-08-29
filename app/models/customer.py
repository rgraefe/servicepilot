from pydantic import StringConstraints
from typing_extensions import Annotated

from app.models.common import ApiModel, Identifier

PostalCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{5}$")]


class Customer(ApiModel):
    customer_id: Identifier
    name: str
    postal_code: PostalCode

