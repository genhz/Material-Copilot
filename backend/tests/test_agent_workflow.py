import asyncio

from fastapi.testclient import TestClient

from agent_workflow.schemas import (
    ExecutionPlan,
    MaterialRequestSpec,
    PlanStep,
    WorkflowRunState,
)
from agent_workflow.service import AgentWorkflowService
from agent_workflow.semantics import extract_semantics
from agent_workflow.state import (
    PlanStatus,
    StepStatus,
    WorkflowStatus,
)
from main import app


def test_semantics_extract_nd_fe_magnetic_request() -> None:
    spec = extract_semantics("请探索钕铁合金磁性性能较优的晶体结构")

    assert spec.required_elements == ["Nd", "Fe"]
    assert spec.allowed_elements == ["Nd", "Fe"]
    assert spec.chemical_system == "Nd-Fe"
    assert spec.objectives[0].property == "dft_mag_density"
    assert spec.objectives[0].target == 0.15
    assert spec.ambiguities


def test_semantics_extract_rare_earth_exclusion() -> None:
    spec = extract_semantics("设计不含稀土元素的高磁密度磁体候选")

    assert "Nd" in spec.excluded_elements
    assert "Dy" in spec.excluded_elements
    assert spec.objectives[0].property == "dft_mag_density"
    assert spec.objectives[0].target == 0.2


def test_websocket_proposes_plan_without_starting_generation() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws") as websocket:
            connected = websocket.receive_json()
            assert connected["type"] == "connected"

            websocket.send_json(
                {
                    "action": "subscribe",
                    "channel": "agent.session",
                    "resource_id": "test-session",
                    "request_id": "subscribe-1",
                }
            )
            assert websocket.receive_json()["type"] == "subscribed"
            assert websocket.receive_json()["type"] == "agent.snapshot"

            websocket.send_json(
                {
                    "action": "agent.message",
                    "session_id": "test-session",
                    "message": "请探索钕铁合金磁密度约 0.15 的晶体结构",
                    "request_id": "message-1",
                }
            )

            plan = None
            event_types: list[str] = []
            for _ in range(10):
                event = websocket.receive_json()
                event_types.append(event["type"])
                if event["type"] == "plan.proposed":
                    plan = event["plan"]
                    break

            assert plan is not None
            assert plan["status"] == "awaiting_confirmation"
            assert plan["request_spec"]["required_elements"] == ["Nd", "Fe"]
            assert plan["request_spec"]["chemical_system"] == "Nd-Fe"
            assert "step.started" not in event_types

            websocket.send_json(
                {
                    "action": "agent.revise",
                    "session_id": "test-session",
                    "plan_id": plan["plan_id"],
                    "revision": plan["revision"],
                    "message": "允许 B，候选数改为 4",
                    "request_id": "revise-1",
                }
            )

            revised_plan = None
            for _ in range(6):
                event = websocket.receive_json()
                if event["type"] == "plan.revised":
                    revised_plan = event["plan"]
                    break

            assert revised_plan is not None
            assert revised_plan["revision"] == 2
            assert revised_plan["request_spec"]["chemical_system"] == "Nd-Fe-B"
            assert "生成 4 个候选" in revised_plan["summary"]


def test_confirmation_starts_workflow_execution() -> None:
    async def run() -> None:
        service = AgentWorkflowService()
        state = service._session("confirm-session")
        queue = service.subscribe("confirm-session")
        plan = ExecutionPlan(
            plan_id="plan-1",
            session_id="confirm-session",
            original_message="生成 Nd-Fe 候选",
            summary="test",
            request_spec=MaterialRequestSpec(
                required_elements=["Nd", "Fe"],
                allowed_elements=["Nd", "Fe"],
                chemical_system="Nd-Fe",
            ),
            steps=[
                PlanStep(
                    id="generate-1",
                    kind="generate",
                    title="generate",
                    description="generate",
                    model_id="chemical_system",
                    conditions={"chemical_system": "Nd-Fe"},
                    num_candidates=8,
                )
            ],
        )
        state.current_plan = plan
        executions: list[str] = []

        async def fake_execute(current_state, current_plan):
            executions.append(current_plan.plan_id)

        service._execute_plan = fake_execute  # type: ignore[method-assign]
        await service.confirm_plan("confirm-session", "plan-1", 1)
        await asyncio.sleep(0)

        assert executions == ["plan-1"]
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event["type"] == "plan.confirmed"

    asyncio.run(run())


def test_required_generation_failure_blocks_downstream_steps(
    monkeypatch,
) -> None:
    async def run() -> None:
        service = AgentWorkflowService()
        state = service._session("failure-session")
        state.workflow = WorkflowRunState(
            workflow_id="workflow-1",
            plan_id="plan-failure",
            session_id="failure-session",
            status=WorkflowStatus.CONFIRMED,
        )
        plan = ExecutionPlan(
            plan_id="plan-failure",
            session_id="failure-session",
            original_message="生成必需候选",
            summary="failure test",
            status=PlanStatus.CONFIRMED,
            request_spec=MaterialRequestSpec(
                required_elements=["Nd", "Fe"],
                allowed_elements=["Nd", "Fe"],
                chemical_system="Nd-Fe",
            ),
            steps=[
                PlanStep(
                    id="generate-required",
                    kind="generate",
                    title="required",
                    description="required",
                    model_id="chemical_system",
                    conditions={"chemical_system": "Nd-Fe"},
                    num_candidates=8,
                    required=True,
                    max_retries=0,
                ),
                PlanStep(
                    id="generate-optional",
                    kind="generate",
                    title="optional",
                    description="optional",
                    model_id="dft_mag_density",
                    conditions={"dft_mag_density": 0.15},
                    num_candidates=8,
                    required=False,
                ),
                PlanStep(
                    id="filter",
                    kind="filter",
                    title="filter",
                    description="filter",
                    depends_on=["generate-required", "generate-optional"],
                    dependency_policy="any",
                    requires_candidates=True,
                ),
                PlanStep(
                    id="rank",
                    kind="rank",
                    title="rank",
                    description="rank",
                    depends_on=["filter"],
                    requires_candidates=True,
                ),
            ],
        )
        state.current_plan = plan
        queue = service.subscribe("failure-session")
        calls: list[str] = []

        class FakeManager:
            async def startup(self) -> None:
                return None

        monkeypatch.setattr(
            "agent_workflow.service.get_generation_manager",
            lambda: FakeManager(),
        )
        monkeypatch.setattr(service, "_preflight_step", lambda *_: None)

        async def fake_run(state, plan, workflow, step, index, total_steps):
            calls.append(step.id)
            step.transition(StepStatus.FAILED)
            step.error_message = "no candidates"
            return False, None

        monkeypatch.setattr(service, "_run_generation_step", fake_run)
        await service._execute_plan(state, plan)

        assert calls == ["generate-required"]
        assert plan.status == PlanStatus.ABORTED
        assert state.workflow is not None
        assert state.workflow.status == WorkflowStatus.ABORTED
        assert plan.steps[1].status == "blocked"
        assert plan.steps[2].status == "blocked"
        assert plan.steps[3].status == "blocked"

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        assert any(event["type"] == "workflow.aborted" for event in events)

    asyncio.run(run())
