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
from agent_workflow.schemas import ExecutionPlan, PlanStep, WorkflowRunState
from generation.exceptions import GenerationError
from generation.manager import get_generation_manager
from generation.model_registry import get_model_spec
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
        plan.updated_at = datetime.now(timezone.utc)
        job_ids: list[str] = []
        candidate_jobs: list[str] = []
        had_optional_failure = False
        total_steps = max(1, len(plan.steps))
        steps_by_id = {step.id: step for step in plan.steps}

        try:
            generation_steps = [
                step for step in plan.steps if step.kind == "generate"
            ]
            for step in generation_steps:
                preflight_error = self._preflight_step(plan, step)
                if preflight_error is None:
                    continue
                step.status = "failed"
                step.error_message = preflight_error
                await self.publish(
                    state.session_id,
                    "step.failed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "step": step.model_dump(mode="json"),
                    },
                )
                if step.required:
                    await self._abort_workflow(
                        state,
                        plan,
                        workflow,
                        step,
                        preflight_error,
                    )
                    return
                had_optional_failure = True

            for index, step in enumerate(plan.steps):
                workflow.current_step_id = step.id

                if step.status in {"failed", "blocked", "skipped", "cancelled"}:
                    continue

                if not self._dependencies_satisfied(
                    step,
                    steps_by_id,
                ):
                    step.status = "blocked"
                    step.error_message = "依赖步骤未成功完成。"
                    workflow.blocked_step_ids = [
                        *workflow.blocked_step_ids,
                        step.id,
                    ]
                    await self.publish(
                        state.session_id,
                        "step.blocked",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step": step.model_dump(mode="json"),
                        },
                    )
                    continue

                step.status = "running"

                if (
                    step.requires_candidates
                    and not candidate_jobs
                ):
                    step.status = "skipped"
                    step.error_message = "没有可用的生成候选。"
                    await self.publish(
                        state.session_id,
                        "step.skipped",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step": step.model_dump(mode="json"),
                        },
                    )
                    await self._abort_workflow(
                        state,
                        plan,
                        workflow,
                        step,
                        "所有生成步骤均未产生可用候选。",
                    )
                    return

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

                success, job_id = await self._run_generation_step(
                    state,
                    plan,
                    workflow,
                    step,
                    index,
                    total_steps,
                )
                if success and job_id:
                    candidate_jobs.append(job_id)
                    job_ids.append(job_id)
                    workflow.job_ids = list(job_ids)
                elif step.required:
                    await self._abort_workflow(
                        state,
                        plan,
                        workflow,
                        step,
                        step.error_message or "生成步骤失败。",
                    )
                    return
                else:
                    had_optional_failure = True
                workflow.progress = (index + 1) / total_steps

            candidate_count = 0
            for job_id in candidate_jobs:
                try:
                    collection = await manager.get_candidates(job_id)
                    candidate_count += len(collection.candidates)
                except Exception:
                    pass

            workflow.candidate_count = candidate_count
            if candidate_count == 0:
                await self._abort_workflow(
                    state,
                    plan,
                    workflow,
                    None,
                    "所有生成步骤均未产生满足约束的候选。",
                )
                return

            if not had_optional_failure:
                workflow.status = "completed"
                plan.status = "completed"
            else:
                workflow.status = "partial"
                plan.status = "partial"

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

    def _preflight_step(
        self,
        plan: ExecutionPlan,
        step: PlanStep,
    ) -> Optional[str]:
        if step.kind != "generate" or not step.model_id:
            return None
        try:
            request = self._generation_request(plan, step)
            request = request.normalized()
            manager = get_generation_manager()
            manager.adapter.preflight(
                get_model_spec(request.model_id or "")
            )
            return None
        except Exception as exc:
            return str(exc)

    def _generation_request(
        self,
        plan: ExecutionPlan,
        step: PlanStep,
        attempt: int = 0,
    ) -> GenerationRequest:
        seed = step.seed
        if seed is not None and attempt:
            seed += attempt
        return GenerationRequest(
            model_id=step.model_id,
            conditions=step.conditions,
            required_elements=plan.request_spec.required_elements,
            allowed_elements=plan.request_spec.allowed_elements,
            excluded_elements=plan.request_spec.excluded_elements,
            num_candidates=step.num_candidates or 8,
            guidance_scale=step.guidance_scale,
            seed=seed,
        )

    def _dependencies_satisfied(
        self,
        step: PlanStep,
        steps_by_id: dict[str, PlanStep],
    ) -> bool:
        if not step.depends_on:
            return True
        statuses = [
            steps_by_id[dependency_id].status
            for dependency_id in step.depends_on
            if dependency_id in steps_by_id
        ]
        if step.dependency_policy == "any":
            return "completed" in statuses
        return bool(statuses) and all(
            status == "completed" for status in statuses
        )

    async def _run_generation_step(
        self,
        state: AgentSessionState,
        plan: ExecutionPlan,
        workflow: WorkflowRunState,
        step: PlanStep,
        index: int,
        total_steps: int,
    ) -> tuple[bool, Optional[str]]:
        manager = get_generation_manager()
        attempts = step.max_retries + 1

        for attempt in range(attempts):
            try:
                request = self._generation_request(plan, step, attempt)
                request = request.normalized()
                job = await manager.submit(request)
            except GenerationError as exc:
                step.error_message = exc.message
                retryable = self._is_retryable(exc.code)
            except Exception as exc:
                step.error_message = str(exc)
                retryable = False
            else:
                step.job_id = job.job_id
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
                            step.status = "completed"
                            return True, job.job_id
                        step.status = "failed"
                        step.error_message = (
                            current.error_message or current.message
                        )
                        retryable = self._is_retryable(
                            current.error_code or ""
                        )
                        break
                    await asyncio.sleep(0.5)

            step.status = "failed"
            if not retryable or attempt >= attempts - 1:
                await self.publish(
                    state.session_id,
                    "step.failed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "step": step.model_dump(mode="json"),
                    },
                )
                return False, None

            await self.publish(
                state.session_id,
                "generation.retry.scheduled",
                {
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.id,
                    "attempt": attempt + 1,
                    "max_attempts": attempts,
                    "message": step.error_message,
                },
            )
            await asyncio.sleep(step.retry_delay_seconds)
            step.status = "running"

        return False, None

    @staticmethod
    def _is_retryable(error_code: str) -> bool:
        return error_code in {
            "GENERATION_FAILED",
            "GENERATION_TIMEOUT",
            "INVALID_OUTPUT",
        }

    async def _abort_workflow(
        self,
        state: AgentSessionState,
        plan: ExecutionPlan,
        workflow: WorkflowRunState,
        failed_step: Optional[PlanStep],
        reason: str,
    ) -> None:
        blocked_ids: list[str] = [
            step.id for step in plan.steps if step.status == "blocked"
        ]
        for step in plan.steps:
            if step.status != "pending":
                continue
            step.status = "blocked"
            step.error_message = "上游步骤失败，未执行。"
            blocked_ids.append(step.id)
            await self.publish(
                state.session_id,
                "step.blocked",
                {
                    "workflow_id": workflow.workflow_id,
                    "step": step.model_dump(mode="json"),
                },
            )

        workflow.status = "failed"
        workflow.failed_step_id = failed_step.id if failed_step else None
        workflow.blocked_step_ids = blocked_ids
        workflow.error_message = reason
        plan.status = "failed"
        await self.publish(
            state.session_id,
            "workflow.aborted",
            {
                "workflow": workflow.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "failed_step_id": workflow.failed_step_id,
                "blocked_step_ids": blocked_ids,
                "reason": reason,
                "recoverable": False,
            },
        )


_service: Optional[AgentWorkflowService] = None


def get_agent_workflow_service() -> AgentWorkflowService:
    global _service
    if _service is None:
        _service = AgentWorkflowService()
    return _service
