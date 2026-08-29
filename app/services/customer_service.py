from app.errors import not_found
from app.models import Customer, Device
from app.repositories.interfaces import CustomerRepository, DeviceRepository


class CustomerService:
    def __init__(self, customers: CustomerRepository, devices: DeviceRepository) -> None:
        self._customers = customers
        self._devices = devices

    async def get_customer(self, customer_id: str) -> Customer:
        customer = await self._customers.get(customer_id)
        if customer is None:
            raise not_found("customer", customer_id)
        return customer

    async def list_devices(self, customer_id: str) -> list[Device]:
        await self.get_customer(customer_id)
        return await self._devices.list_for_customer(customer_id)
