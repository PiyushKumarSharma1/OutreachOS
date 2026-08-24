from outreachos.exports import export_campaign_csv


def test_export_csv(engine, campaign, tmp_path):
    engine.full_cycle(campaign.name, limit=10)
    res = export_campaign_csv(engine.store, campaign.name, out_dir=str(tmp_path))
    assert res["rows"] > 0
    from pathlib import Path
    p = Path(res["path"])
    assert p.exists()
    content = p.read_text()
    assert "first_name" in content and "outreach_state" in content
