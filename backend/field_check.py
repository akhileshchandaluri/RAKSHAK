"""Observed event summaries and a reproducible, unfitted model comparison."""

from simulation import ScenarioRequest, run_scenario


EVENTS = (
    {
        "name": "Rajasthan · 15 May 2023",
        "loss_mw": 7120,
        "initial_hz": 49.98,
        "nadir_hz": 49.40,
        "source": "https://nerpc.gov.in/wp-content/uploads/2023/10/Minutes-of-the-61-260620230506.pdf",
    },
    {
        "name": "Khavda · 13 May 2026",
        "loss_mw": 8963,
        "initial_hz": 49.95,
        "nadir_hz": 49.39,
        "source": "https://erpc.gov.in/meetings/multiple-document/download/eyJpdiI6IjYzV2FFdXk2OGdpOFRXR2s5MHZPSXc9PSIsInZhbHVlIjoiYTl6WFlUdVZnVzdnTkg4WUtWd2hQQT09IiwibWFjIjoiYWUxYzA4NjgyNWU2M2M2YmQyZTY2OTMyNzg5NDYwMmQzNWU2MmEyMDRhMjc1NGY0MTEzYjcxNWZmZjRkN2E1OSIsInRhZyI6IiJ9",
    },
)


def compare_field_events():
    comparisons = []
    for event in EVENTS:
        for base_mw in (200_000, 250_000):
            scenario = ScenarioRequest(mode="ufls", generation_loss=event["loss_mw"] / base_mw)
            result = run_scenario(scenario, duration=40, initial_frequency_hz=event["initial_hz"])
            comparisons.append({
                **event,
                "assumed_base_mw": base_mw,
                "modeled_nadir_hz": result["nadir"],
                "nadir_error_hz": round(result["nadir"] - event["nadir_hz"], 3),
                "modeled_aufls_blocks": result["feeder_trips"],
            })
    return comparisons
