from pathlib import Path

from generation.campaign_store import CampaignStore
from generation.schemas import (
    CampaignJob,
    CampaignRunState,
    GenerationRequest,
)
from generation.store import utc_now


def test_campaign_store_round_trip(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path)
    request = GenerationRequest(
        model_id="dft_mag_density",
        conditions={"dft_mag_density": 0.15},
    ).normalized()
    campaign = CampaignJob(
        campaign_id=store.new_id(),
        name="test campaign",
        runs=[
            CampaignRunState(
                run_id=store.new_id(),
                model_id="dft_mag_density",
                model_label="磁密度生成",
                conditions=request.conditions,
                request=request,
            )
        ],
        created_at=utc_now(),
    )

    store.create(campaign)
    loaded = store.get(campaign.campaign_id)

    assert loaded.name == "test campaign"
    assert loaded.runs[0].request.conditions == {"dft_mag_density": 0.15}
