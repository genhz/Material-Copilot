"""Execute non-generation workflow steps through existing material tools."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from agent_workflow.schemas import (
    ExecutionPlan,
    PlanStep,
    WorkflowResult,
    WorkflowRunState,
)
from agent_workflow.state import (
    PlanStatus,
    StepStatus,
    WorkflowResultStatus,
    WorkflowStatus,
)


logger = logging.getLogger(__name__)

PublishCallback = Callable[
    [str, str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]
AbortCallback = Callable[
    [Any, ExecutionPlan, WorkflowRunState, PlanStep | None, str],
    Awaitable[None],
]


class WorkflowToolExecutor:
    """Run material lookup, substitution, and science chat plan steps."""

    async def execute(
        self,
        state: Any,
        plan: ExecutionPlan,
        publish: PublishCallback,
        abort: AbortCallback,
    ) -> None:
        workflow = state.workflow
        assert workflow is not None
        workflow.transition(WorkflowStatus.RUNNING)
        plan.transition(PlanStatus.EXECUTING)
        steps_by_id = {step.id: step for step in plan.steps}
        outputs: dict[str, dict[str, Any]] = {}
        total_steps = max(1, len(plan.steps))

        try:
            for index, step in enumerate(plan.steps):
                workflow.current_step_id = step.id
                if not self._dependencies_satisfied(step, steps_by_id):
                    step.transition(StepStatus.BLOCKED)
                    step.error_message = "依赖步骤未成功完成。"
                    await abort(
                        state,
                        plan,
                        workflow,
                        step,
                        step.error_message,
                    )
                    return

                step.transition(StepStatus.RUNNING)
                await publish(
                    state.session_id,
                    "step.started",
                    {
                        "workflow_id": workflow.workflow_id,
                        "step": step.model_dump(mode="json"),
                    },
                )
                try:
                    output = await self._run_step(step, outputs)
                except Exception as exc:
                    step.transition(StepStatus.FAILED)
                    step.error_message = str(exc)
                    await publish(
                        state.session_id,
                        "step.failed",
                        {
                            "workflow_id": workflow.workflow_id,
                            "step": step.model_dump(mode="json"),
                        },
                    )
                    await abort(
                        state,
                        plan,
                        workflow,
                        step,
                        str(exc),
                    )
                    return

                step.output = output
                step.transition(StepStatus.COMPLETED)
                step.progress = 1.0
                outputs[step.id] = output
                workflow.progress = (index + 1) / total_steps
                await publish(
                    state.session_id,
                    "step.completed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "step": step.model_dump(mode="json"),
                    },
                )

            result = self._build_result(plan, outputs)
            workflow.transition(WorkflowStatus.COMPLETED)
            workflow.result = result
            plan.transition(PlanStatus.COMPLETED)
            await publish(
                state.session_id,
                "workflow.completed",
                {
                    "workflow": workflow.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                    "result": result.model_dump(mode="json"),
                },
            )
            await publish(
                state.session_id,
                "assistant.completed",
                {
                    "message": result.message,
                    "action": "render" if result.material_data else "chat",
                    "material_data": result.material_data,
                },
            )
        except asyncio.CancelledError:
            workflow.transition(WorkflowStatus.CANCELLED)
            plan.transition(PlanStatus.CANCELLED)
            await publish(state.session_id, "workflow.cancelled", {})
        except Exception as exc:
            logger.exception("Non-generation workflow execution failed")
            workflow.transition(WorkflowStatus.FAILED)
            workflow.error_message = str(exc)
            plan.transition(PlanStatus.FAILED)
            await publish(
                state.session_id,
                "workflow.failed",
                {
                    "workflow": workflow.model_dump(mode="json"),
                    "error": str(exc),
                },
            )

    async def _run_step(
        self,
        step: PlanStep,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        tool_name = str(step.inputs.get("_tool") or "")
        if tool_name == "material_search":
            from skills.material_search import MaterialSearchTool

            formula = str(step.inputs.get("formula") or "")
            raw = await MaterialSearchTool()._arun(formula)
            return json.loads(raw)

        if tool_name == "element_substitution":
            from skills.element_substitution import ElementSubstitutionTool

            cif = str(step.inputs.get("cif") or "")
            formula = str(step.inputs.get("formula") or "")
            if not cif:
                for dependency_id in step.depends_on:
                    dependency_output = outputs.get(dependency_id, {})
                    cif = str(dependency_output.get("cif") or "")
                    formula = formula or str(
                        dependency_output.get("formula") or ""
                    )
                    if cif:
                        break
            substitutions = dict(step.inputs.get("substitutions") or {})
            raw = await ElementSubstitutionTool()._arun(
                cif=cif,
                substitutions=substitutions,
                current_formula=formula,
            )
            return json.loads(raw)

        if tool_name == "chat":
            from skills.chat import ChatTool

            message = str(step.inputs.get("message") or "")
            reply = await ChatTool()._arun(message=message)
            return {"message": reply}

        raise RuntimeError(f"不支持的工具步骤：{tool_name}")

    @staticmethod
    def _build_result(
        plan: ExecutionPlan,
        outputs: dict[str, dict[str, Any]],
    ) -> WorkflowResult:
        material_data = None
        message = None
        for step in reversed(plan.steps):
            output = outputs.get(step.id, {})
            if output.get("cif"):
                material_data = output
                message = (
                    f"已生成替换后的结构 {output.get('formula', '')}。"
                    if step.kind == "element_substitution"
                    else f"已查询到 {output.get('formula', '')}。"
                )
                break
            if step.kind == "science_chat" and output.get("message"):
                message = str(output["message"])
                break
        return WorkflowResult(
            status=WorkflowResultStatus.COMPLETED,
            task_type=plan.request_spec.task_type,
            steps=[
                {
                    "step_id": step.id,
                    "kind": step.kind,
                    "status": step.status,
                    "output": outputs.get(step.id, {}),
                    "error_message": step.error_message,
                }
                for step in plan.steps
            ],
            message=message,
            material_data=material_data,
        )

    @staticmethod
    def _dependencies_satisfied(
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
