from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from inspection_utils.logging_tools import utc_now_str


@dataclass(slots=True)
class BagRecordingHandle:
    output_path: str
    command: list[str]
    process: subprocess.Popen[str] | None = None
    topics: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now_str)

    def to_dict(self) -> dict[str, object]:
        return {
            'output_path': self.output_path,
            'command': list(self.command),
            'topics': list(self.topics),
            'started_at': self.started_at,
            'running': self.process is not None and self.process.poll() is None,
        }


@dataclass(slots=True)
class BagManager:
    ros2_executable: str = 'ros2'
    storage_id: str = 'mcap'
    storage_config_uri: str = ''
    process: subprocess.Popen[str] | None = None
    last_command: list[str] = field(default_factory=list)
    active_handle: BagRecordingHandle | None = None

    def ros2_available(self) -> bool:
        return shutil.which(self.ros2_executable) is not None

    def build_record_command(self, *, output_path: str | Path, topics: Sequence[str], storage_id: str | None = None, storage_config_uri: str | None = None) -> list[str]:
        resolved_storage = str(storage_id or self.storage_id or '').strip()
        resolved_storage_config = str(storage_config_uri or self.storage_config_uri or '').strip()
        command = [self.ros2_executable, 'bag', 'record', '-o', str(output_path)]
        if resolved_storage:
            command.extend(['-s', resolved_storage])
        if resolved_storage_config:
            command.extend(['--storage-config-file', resolved_storage_config])
        command.extend(str(topic) for topic in topics)
        return command

    def build_play_command(self, *, bag_path: str | Path, paused: bool = True, rate: float = 1.0, storage_id: str | None = None) -> list[str]:
        command = [self.ros2_executable, 'bag', 'play', str(bag_path), '--rate', str(rate)]
        resolved_storage = str(storage_id or self.storage_id or '').strip()
        if resolved_storage:
            command.extend(['--storage', resolved_storage])
        if paused:
            command.append('--start-paused')
        return command

    def build_info_command(self, *, bag_path: str | Path) -> list[str]:
        return [self.ros2_executable, 'bag', 'info', str(bag_path)]

    def start_recording(self, *, output_path: str | Path, topics: Sequence[str], storage_id: str | None = None, storage_config_uri: str | None = None) -> BagRecordingHandle | None:
        command = self.build_record_command(output_path=output_path, topics=topics, storage_id=storage_id, storage_config_uri=storage_config_uri)
        self.last_command = list(command)
        if not self.ros2_available():
            self.active_handle = None
            return None
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        self.process = process
        self.active_handle = BagRecordingHandle(output_path=str(output_path), command=command, process=process, topics=[str(topic) for topic in topics])
        return self.active_handle

    def stop_recording(self) -> bool:
        if self.process is None:
            return False
        self.process.terminate()
        try:
            self.process.wait(timeout=5.0)
        except Exception:
            self.process.kill()
        self.process = None
        return True

    def snapshot(self) -> dict[str, object]:
        if self.active_handle is None:
            return {'enabled': False, 'command': list(self.last_command)}
        return {'enabled': True, **self.active_handle.to_dict()}
