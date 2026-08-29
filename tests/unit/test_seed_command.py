import pytest

from app.seed import seed_firestore


@pytest.mark.asyncio
async def test_seed_command_requires_explicit_confirmation() -> None:
    with pytest.raises(RuntimeError, match="--confirm"):
        await seed_firestore(False)
