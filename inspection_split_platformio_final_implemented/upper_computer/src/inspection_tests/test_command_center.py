from station_bridge.command_center import CommandCenter


def test_command_center_invalidates_old_generation_pending_commands():
    center = CommandCenter(active_generation=1)
    center.register(1, 'feed', 'T1', 1, 'B1')
    invalidated = center.rollover_session(2)
    assert len(invalidated) == 1
    assert invalidated[0].state == 'superseded'
    assert center.resolve(1) is None
