from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    name: str
    semantic: str
    expects_ack: bool = True
    expects_done: bool = False


COMMANDS: dict[str, CommandDefinition] = {
    'feed': CommandDefinition(name='feed', semantic='FEED_ONE', expects_ack=True, expects_done=False),
    'sort': CommandDefinition(name='sort', semantic='SORT_TO_BIN', expects_ack=True, expects_done=True),
    'reset': CommandDefinition(name='reset', semantic='RESET_FAULT', expects_ack=True, expects_done=False),
    'heartbeat': CommandDefinition(name='heartbeat', semantic='HEARTBEAT', expects_ack=False, expects_done=False),
}


def get_command(name: str) -> CommandDefinition:
    return COMMANDS[name]
