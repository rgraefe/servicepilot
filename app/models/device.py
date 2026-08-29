from app.models.common import ApiModel, Identifier


class Device(ApiModel):
    device_id: Identifier
    customer_id: Identifier
    model: str
    serial_number: str

