"""Filesystem-backed storage for multi-model generation campaigns."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from generation.exceptions import GenerationError
from generation.schemas import CampaignJob
from generation.store import GenerationStore, utc_now


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class CampaignStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, campaign: CampaignJob) -> CampaignJob:
        self.save(campaign)
        return campaign

    def get(self, campaign_id: str) -> CampaignJob:
        path = self.path(campaign_id)
        if not path.is_file():
            raise GenerationError(
                "CAMPAIGN_NOT_FOUND",
                f"Campaign 不存在：{campaign_id}",
                status_code=404,
            )
        return CampaignJob.model_validate(GenerationStore.read_json(path))

    def save(self, campaign: CampaignJob) -> None:
        self.write_json(
            self.path(campaign.campaign_id),
            campaign.model_dump(mode="json"),
        )

    def update(self, campaign_id: str, **updates) -> CampaignJob:
        campaign = self.get(campaign_id)
        updates["updated_at"] = utc_now()
        payload = campaign.model_dump(mode="python")
        payload.update(updates)
        updated = CampaignJob.model_validate(payload)
        self.save(updated)
        return updated

    def path(self, campaign_id: str) -> Path:
        if not UUID_PATTERN.fullmatch(campaign_id):
            raise GenerationError(
                "CAMPAIGN_NOT_FOUND",
                f"Campaign 不存在：{campaign_id}",
                status_code=404,
            )
        return self.root / f"{campaign_id}.json"

    def new_id(self) -> str:
        return str(uuid.uuid4())

    def mark_stale_running_failed(self) -> int:
        count = 0
        for path in self.root.glob("*.json"):
            try:
                campaign = CampaignJob.model_validate(
                    GenerationStore.read_json(path)
                )
            except Exception:
                continue
            if campaign.status in {"queued", "running"}:
                self.update(
                    campaign.campaign_id,
                    status="failed",
                    completed_at=utc_now(),
                )
                count += 1
        return count

    @staticmethod
    def write_json(path: Path, payload: dict) -> None:
        GenerationStore.write_json(path, payload)
