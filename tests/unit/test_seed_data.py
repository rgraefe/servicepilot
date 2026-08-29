from app.seed_data import load_demo_data


def test_demo_seed_has_required_phase_two_entities() -> None:
    demo = load_demo_data()
    assert len(demo.customers) == 5
    assert len(demo.devices) == 8
    assert len(demo.tickets) == 10
    assert len(demo.appointments) == 8
    assert len(demo.error_codes) >= 3
    assert all(
        any(device.customer_id == customer.customer_id for customer in demo.customers)
        for device in demo.devices
    )
    assert all(
        any(device.device_id == ticket.device_id for device in demo.devices)
        for ticket in demo.tickets
    )
