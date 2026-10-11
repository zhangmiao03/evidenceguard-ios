"""Host-owned execution boundary, inspired by MiiMiao's frozen run context.

The current mobile executor is bounded-chat-v1, not the desktop Codex binary.
Memory is source material and cannot expand the frozen tool allowlist.
"""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ExecutionContract:
    mode: str
    allowed_tools: tuple[str, ...]
    camera_id: str | None
    skill_id: str | None
    executor: str = 'bounded-chat-v1'
    max_steps: int = 8
    history_char_budget: int = 18000

    def public(self): return asdict(self)
    def check_tool(self, name):
        if name not in self.allowed_tools: raise ValueError('本轮未授权此工具：'+name)


def recent_context(runs, *, budget=18000):
    """Keep complete user/assistant pairs, newest first in the budget, then chronological."""
    pairs = []
    for run in reversed(runs[-16:]):
        text, answer = run.get('message',''), run.get('text') or ''
        if len(text)+len(answer) > budget: break
        budget -= len(text)+len(answer)
        pair = [dict(role='user',content=text)]
        if answer: pair.append(dict(role='assistant',content=answer))
        pairs.append(pair)
    return [message for pair in reversed(pairs) for message in pair]
