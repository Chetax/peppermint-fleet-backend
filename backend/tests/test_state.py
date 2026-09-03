import pytest

from state import fleet_state, update_robot, get_snapshot


@pytest.fixture(autouse=True)
def clear_fleet_state():
    """
    Runs automatically before every test in this file. Clears the
    shared fleet_state dict so tests don't leak data into each other
    -- without this, test order could change results.
    """
    fleet_state.clear()
    yield
    fleet_state.clear()


def test_update_robot_stores_correct_data():
    """Basic correctness: update_robot stores values keyed by robot_id."""
    incoming = {
        "robot_id": "r1",
        "x": 10.0,
        "y": 20.0,
        "status": "idle",
        "battery": 90.0,
    }

    update_robot(incoming)

    assert "r1" in fleet_state
    assert fleet_state["r1"]["x"] == 10.0
    assert fleet_state["r1"]["y"] == 20.0
    assert fleet_state["r1"]["status"] == "idle"
    assert fleet_state["r1"]["battery"] == 90.0
    # last_updated should exist and be a non-empty string (ISO timestamp)
    assert fleet_state["r1"]["last_updated"]


def test_snapshot_is_independent_copy():
    """
    get_snapshot() must return a copy, not a live reference to
    fleet_state. If a caller holds a snapshot and fleet_state is
    later updated, the snapshot must NOT change -- otherwise REST
    responses could reflect a mix of old and new data mid-serialization.
    """
    update_robot({
        "robot_id": "r1", "x": 1.0, "y": 1.0,
        "status": "idle", "battery": 50.0,
    })

    snapshot = get_snapshot()
    assert snapshot["r1"]["x"] == 1.0

    # Now update fleet_state AFTER taking the snapshot.
    update_robot({
        "robot_id": "r1", "x": 999.0, "y": 999.0,
        "status": "active", "battery": 10.0,
    })

    # The earlier snapshot must still show the OLD value.
    assert snapshot["r1"]["x"] == 1.0
    # While fleet_state itself reflects the new value.
    assert fleet_state["r1"]["x"] == 999.0


def test_update_robot_raises_on_missing_key():
    """
    A malformed update (missing a required field) should raise loudly,
    not silently store partial/garbage data -- this is trusted internal
    data (from our own publishers), so a missing key signals a bug in
    our own pipeline that we want surfaced, not hidden.
    """
    incomplete = {
        "robot_id": "r1",
        "x": 10.0,
        # missing "y", "status", "battery"
    }

    with pytest.raises(KeyError):
        update_robot(incomplete)

    # And nothing should have been stored for r1.
    assert "r1" not in fleet_state