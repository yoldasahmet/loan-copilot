"""A stand-in for the provider call: tests queue replies, llm.py does everything else."""

import json

from loancopilot.llm import Reply, Request


class FakeLlm:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.requests: list[Request] = []

    def queue(self, reply: str | dict) -> None:
        self.replies.append(reply if isinstance(reply, str) else json.dumps(reply))

    def call(self, req: Request) -> Reply:
        self.requests.append(req)
        return Reply(self.replies.pop(0), "fake-model", 120, 40)
