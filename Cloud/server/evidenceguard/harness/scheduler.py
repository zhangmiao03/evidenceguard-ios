"""Small TaskEnvelope boundary, adapted to camera workloads from MiiMiao v1.0."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str
    workload: str
    skill_id: str | None = None
    run_id: str | None = None
    schema_version: str = 'EvidenceGuardTask/v1'

class TaskScheduler:
    def __init__(self, limits=None, capacity=24):
        self.limits = limits or {'chat': 3, 'history': 2, 'observation': 1, 'camera': 2}
        self.capacity = capacity
        self.gates = {lane: asyncio.Semaphore(size) for lane, size in self.limits.items()}
        self.jobs = {}

    def submit(self, envelope: TaskEnvelope, operation: Callable[[], Awaitable]):
        if envelope.task_id in self.jobs:
            return self.jobs[envelope.task_id]
        if envelope.workload not in self.gates:
            raise ValueError('未知任务类型')
        if len(self.jobs) >= self.capacity:
            raise ValueError('任务队列已满，请稍后重试')
        async def execute():
            async with self.gates[envelope.workload]:
                return await operation()
        task = asyncio.create_task(execute())
        self.jobs[envelope.task_id] = task
        def finished(_):
            if self.jobs.get(envelope.task_id) is task:
                self.jobs.pop(envelope.task_id, None)
        task.add_done_callback(finished)
        return task

    async def shutdown(self):
        jobs = list(self.jobs.values())
        for job in jobs: job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
