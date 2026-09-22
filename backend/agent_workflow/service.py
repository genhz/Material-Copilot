"""Plan-first agent session service with realtime workflow events."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agent_workflow.planner import WorkflowPlanner
from agent_workflow.schemas import ExecutionPlan, WorkflowRunState
from generation.manager import get_generation_manager
from generation.schemas import GenerationRequest


logger = logging.getLogger(__name__)


@dataclass
class AgentSessionState:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    current_plan: Optional[ExecutionPlan] = None
    workflow: Optional[WorkflowRunState] = None
    events: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=1000)
    )
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    sequence: int = 0
    task: Optional[asyncio.Task] = None


class AgentWorkflowService:
    """Maintain plan revisions and execute only confirmed plans."""

    def __init__(self):
        self._sessions: dict[str, AgentSessionState] = {}
        self._planner = None

    @property
    def planner(self) -> WorkflowPlanner:
        if self._planner is None:
            self._planner = WorkflowPlanner()
        return self._planner

    def _session(self, session_id: str) -> AgentSessionState:
        state = self._sessions.get(session_id)
        if state is None:
            state = AgentSessionState(session_id=session_id)
            self._sessions[session_id] = state
        return state

    async def publish(
        self,
        session_id: str,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        state = self._session(session_id)
        state.sequence += 1
        event = {
            "type": event_type,
            "channel": "agent.session",
            "resource_id": session_id,
            "sequence": state.sequence,
            "server_time": datetime.now(timezone.utc).isoformat(),
            **(payload or {}),
        }
        state.events.append(event)
        for queue in list(state.subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        return event

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._session(session_id).subscribers.add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        state = self._session(session_id)
        state.subscribers.discard(queue)

    def snapshot(
        self,
        session_id: str,
        last_sequence: int = 0,
    ) -> dict[str, Any]:
        state = self._session(session_id)
        return {
            "messages": state.messages,
            "plan": (
                state.current_plan.model_dump(mode="json")
                if state.current_plan
                else None
            ),
            "workflow": (
                state.workflow.model_dump(mode="json")
                if state.workflow
                else None
            ),
            "last_sequence": state.sequence,
            "events": (
                []
                if last_sequence <= 0
                else [
                    event
                    for event in state.events
                    if int(event.get("sequence", 0)) > last_sequence
                ]
            ),
        }

    async def handle_message(self, session_id: str, message: str) -> None:
        state = self._session(session_id)
        state.messages.append({"role": "user", "content": message})
        await self.publish(session_id, "agent.run.started")
        await self.publish(
            session_id,
            "assistant.delta",
            {"content": "正在解析材料范围、元素约束和性能目标。\n"},
        )

        plan = await self.planner.propose(
            session_id=session_id,
            message=message,
            history=state.messages[-12:],
        )
        if plan is None:
            from agent import execute_agent

            result = await execute_agent(message, state.messages[-12:])
            state.messages.append(
                {"role": "assistant", "content": result.reply}
            )
            await self.publish(
                session_id,
                "assistant.completed",
                {
                    "message": result.reply,
                    "action": result.action,
                    "material_data": (
                        result.material_data.to_dict()
                        if result.material_data
                        else None
                    ),
                    "job_id": result.job_id,
                    "campaign_id": result.campaign_id,
                },
            )
            return

        state.current_plan = plan
        completion_message = (
            "执行计划已生成，请确认或修改后开始执行。"
        )
        state.messages.append(
            {"role": "assistant", "content": completion_message}
        )
        await self.publish(
            session_id,
            "assistant.delta",
            {"content": "已生成执行计划，请确认或修改后开始执行。\n"},
        )
        await self.publish(
            session_id,
            "plan.proposed",
            {"plan": plan.model_dump(mode="json")},
        )
        await self.publish(
            session_id,
            "assistant.completed",
            {"message": completion_message, "plan_id": plan.plan_id},
        )

    async def revise_plan(
        self,
        session_id: str,
        plan_id: str,
        revision: int,
        instruction: str,
    ) -> None:
        state = self._session(session_id)
        plan = state.current_plan
        if plan is None or plan.plan_id != plan_id:
            await self.publish(
                session_id,
                "error",
                {"code": "PLAN_NOT_FOUND", "message": "执行计划不存在。"},
            )
            return
        if plan.revision != revision:
            await self.publish(
                session_id,
                "error",
                {
                    "code": "PLAN_REVISION_STALE",
                    "message": "执行计划已被更新，请使用最新版本。",
                },
            )
            return

        state.messages.append(
            {"role": "user", "content": f"修改执行计划：{instruction}"}
        )
        await self.publish(session_id, "plan.revising", {"plan_id": plan_id})
        revised = await self.planner.propose(
            session_id=session_id,
            message=plan.original_message,
            history=state.messages[-12:],
            previous_plan=plan,
            revision_instruction=instruction,
        )
        if revised is None:
            await self.publish(
                session_id,
                "error",
                {"code": "REVISION_FAILED", "message": "无法根据修改要求更新计划。"},
            )
            return
        state.current_plan = revised
        await self.publish(
            session_id,
            "plan.revised",
            {"plan": revised.model_dump(mode="json")},
        )

    async def confirm_plan(
        self,
        session_id: str,
        plan_id: str,
        revision: int,
    ) -> None:
        state = self._session(session_id)
        plan = state.current_plan
        if plan is None or plan.plan_id != plan_id:
            await self.publish(
                session_id,
                "error",
                {"code": "PLAN_NOT_FOUND", "message": "执行计划不存在。"},
            )
            return
        if plan.revision != revision:
            await self.publish(
                session_id,
                "error",
                {
                    "code": "PLAN_REVISION_STALE",
                    "message": "执行计划版本不匹配，请重新确认最新版本。",
                },
            )
            return
        if state.task and not state.task.done():
            await self.publish(
                session_id,
                "error",
                {"code": "WORKFLOW_ALREADY_RUNNING", "message": "已有任务正在执行。"},
            )
            return

        plan.status = "confirmed"
        workflow = WorkflowRunState(
            workflow_id=str(uuid.uuid4()),
            plan_id=plan.plan_id,
            session_id=session_id,
        )
        state.workflow = workflow
        await self.publish(
            session_id,
            "plan.confirmed",
            {
                "plan_id": plan.plan_id,
                "revision": plan.revision,
                "workflow_id": workflow.workflow_id,
            },
        )
        state.task = asyncio.create_task(self._execute_plan(state, plan))

    async def cancel_workflow(self, session_id: str) -> None:
        state = self._session(session_id)
        if state.task and not state.task.done():
            state.task.cancel()
        manager = get_generation_manager()
        if state.workflow:
            for job_id in state.workflow.job_ids:
                try:
                    await manager.cancel(job_id)
                except Exception:
                    pass
            state.workflow.status = "cancelled"
        if state.current_plan:
            state.current_plan.status = "cancelled"
        await self.publish(session_id, "workflow.cancelled")

    async def clear_session(self, session_id: str) -> None:
        state = self._session(session_id)
        if state.task and not state.task.done():
            state.task.cancel()
        state.messages.clear()
        state.current_plan = None
        state.workflow = None
        state.events.clear()
        state.sequence = 0
        await self.publish(session_id, "agent.cleared")

    async def _execute_plan(
        self,
        state: AgentSessionState,
        plan: ExecutionPlan,
    ) -> None:
        manager = get_generation_manager()
        await manager.startup()
        workflow = state.workflow
        assert workflow is not None
        workflow.status = "running"
        plan.status = "executing"
        job_ids: list[str] = []
        candidate_jobs: list[str] = []
        total_steps = max(1, len(plan.steps))

        try:
            for index, step in enumerate(plan.steps):
                workflow.current_step_id = step.id
                step.status = "running"

                if step.kind != "generate":
                    step.status = "completed"
                    step.progress = 1.0
                    await self.publish(
                        state.session_id,
                        "step.started",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step": step.model_dump(mode="json"),
                        },
                    )
                    await self.publish(
                        state.session_id,
                        "step.completed",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step": step.model_dump(mode="json"),
                        },
                    )
                    workflow.progress = (index + 1) / total_steps
                    continue

                try:
                    request = GenerationRequest(
                        model_id=step.model_id,
                        conditions=step.conditions,
                        required_elements=plan.request_spec.required_elements,
                        allowed_elements=plan.request_spec.allowed_elements,
                        excluded_elements=plan.request_spec.excluded_elements,
                        num_candidates=step.num_candidates or 8,
                        guidance_scale=step.guidance_scale,
                        seed=step.seed,
                    )
                    job = await manager.submit(request)
                except Exception as exc:
                    step.status = "failed"
                    step.error_message = str(exc)
                    await self.publish(
                        state.session_id,
                        "step.failed",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step": step.model_dump(mode="json"),
                        },
                    )
                    continue
                step.job_id = job.job_id
                job_ids.append(job.job_id)
                workflow.job_ids = list(job_ids)
                await self.publish(
                    state.session_id,
                    "step.started",
                    {
                        "workflow_id": workflow.workflow_id,
                        "step": step.model_dump(mode="json"),
                        "job_id": job.job_id,
                    },
                )

                while True:
                    current = await manager.get_job(job.job_id)
                    step.progress = current.progress
                    workflow.progress = (
                        index + current.progress
                    ) / total_steps
                    await self.publish(
                        state.session_id,
                        "step.progress",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step_id": step.id,
                            "job_id": job.job_id,
                            "progress": current.progress,
                            "message": current.message,
                        },
                    )
                    if current.status in {
                        "completed",
                        "failed",
                        "cancelled",
                    }:
                        if current.status == "completed":
                            candidate_jobs.append(job.job_id)
                            step.status = "completed"
                        else:
                            step.status = "failed"
                            step.error_message = (
                                current.error_message or current.message
                            )
                        break
                    await asyncio.sleep(0.5)

                await self.publish(
                    state.session_id,
                    (
                        "step.completed"
                        if step.status == "completed"
                        else "step.failed"
                    ),
                    {
                        "workflow_id": workflow.workflow_id,
                        "step": step.model_dump(mode="json"),
                    },
                )
                workflow.progress = (index + 1) / total_steps

            candidate_count = 0
            for job_id in candidate_jobs:
                try:
                    collection = await manager.get_candidates(job_id)
                    candidate_count += len(collection.candidates)
                except Exception:
                    pass

            workflow.candidate_count = candidate_count
            if candidate_jobs and len(candidate_jobs) == len(job_ids):
                workflow.status = "completed"
                plan.status = "completed"
            elif candidate_jobs:
                workflow.status = "partial"
                plan.status = "partial"
            else:
                workflow.status = "failed"
                plan.status = "failed"

            await self.publish(
                state.session_id,
                "workflow.completed",
                {
                    "workflow": workflow.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                },
            )
        except asyncio.CancelledError:
            workflow.status = "cancelled"
            plan.status = "cancelled"
            await self.publish(state.session_id, "workflow.cancelled")
        except Exception as exc:
            logger.exception("Agent workflow execution failed")
            workflow.status = "failed"
            workflow.error_message = str(exc)
            plan.status = "failed"
            await self.publish(
                state.session_id,
                "workflow.failed",
                {
                    "workflow": workflow.model_dump(mode="json"),
                    "error": str(exc),
                },
            )


_service: Optional[AgentWorkflowService] = None


def get_agent_workflow_service() -> AgentWorkflowService:
    global _service
    if _service is None:
        _service = AgentWorkflowService()
    return _service
