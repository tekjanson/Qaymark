"""Harness control-room state engine scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Project:
    id: str
    title: str
    status: str = "queued"
    priority: int = 0


@dataclass
class ChatMessage:
    role: str
    text: str


@dataclass
class HarnessBoard:
    projects: list[Project] = field(default_factory=list)
    chat: list[ChatMessage] = field(default_factory=list)
    running: list[Project] = field(default_factory=list)
    paused: bool = False

    def add_project(self, project_id: str, title: str, priority: int = 0) -> None:
        existing = self._project(project_id)
        if existing is not None:
            existing.title = title
            existing.priority = priority
            if existing.status != "running":
                existing.status = "queued"
            return
        self.projects.append(Project(project_id, title, "queued", priority))

    def pull_next(self) -> dict | None:
        if self.paused:
            return None
        queued = [project for project in self.projects if project.status == "queued"]
        if not queued:
            return None
        queued.sort(key=lambda item: (-item.priority, item.title.lower(), item.id))
        project = queued[0]
        project.status = "running"
        if not any(item.id == project.id for item in self.running):
            self.running.append(project)
        return self._project_view(project)

    def pause_queue(self) -> None:
        self.paused = True

    def resume_queue(self) -> None:
        self.paused = False

    def post_message(self, role: str, text: str) -> None:
        self.chat.append(ChatMessage(role, text))

    def snapshot(self) -> dict:
        queued = [self._project_view(p) for p in self.projects if p.status == "queued"]
        return {
            "paused": self.paused,
            "projects": [self._project_view(project) for project in self.projects],
            "running": [self._project_view(project) for project in self.running],
            "queued": queued,
            "chat": [message.__dict__ for message in self.chat],
        }

    def _project(self, project_id: str) -> Project | None:
        for project in self.projects:
            if project.id == project_id:
                return project
        return None

    @staticmethod
    def _project_view(project: Project) -> dict:
        return {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "priority": project.priority,
        }
