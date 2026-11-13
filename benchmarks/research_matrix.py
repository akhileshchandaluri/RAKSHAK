"""Paired seed experiments; same engine and frozen inventory as the live dashboard."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import math
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from inventory import InventoryStore
from simulation import ScenarioRequest, run_scenario


def experiment(job):
    seed, participation, magnitude, inventory = job
    rows = []
    for mode in ('ufls', 'rakshak'):
        scenario = ScenarioRequest(mode=mode, seed=seed, participation=participation, generation_loss=magnitude)
        result = run_scenario(scenario, inventory=inventory)
        result.pop('trace')
        rows.append(dict(seed=seed, participation=participation, magnitude=magnitude, inventory_revision=inventory['revision'], **result))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--seeds', type=int, default=20, choices=[20], help='Fixed 20-seed protocol (19 degrees of freedom)')
    parser.add_argument('--output', default='benchmarks/results')
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    inventory = InventoryStore().snapshot()
    jobs = [(seed, participation, magnitude, inventory) for seed in range(args.seeds) for participation in (0, .25, .5, .75, 1) for magnitude in (.1, .18, .35)]
    rows = []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(experiment, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            rows.extend(future.result())
            if i % 10 == 0 or i == len(jobs):
                print(f'{i}/{len(jobs)} paired experiments; {time.monotonic()-started:.0f}s', flush=True)
    rows.sort(key=lambda r: (r['magnitude'], r['participation'], r['seed'], r['mode']))
    with (root/'paired_runs.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summaries = []
    metrics = ['nadir', 'critical_energy_not_served_wh', 'total_unserved_wh', 'longest_device_pause_s', 'peak_post_shed_load', 'feeder_trips', 'relief_shortfall_kw']
    for magnitude in (.1, .18, .35):
        for participation in (0, .25, .5, .75, 1):
            group = [r for r in rows if r['magnitude']==magnitude and r['participation']==participation]
            paired = {mode: sorted((r for r in group if r['mode']==mode), key=lambda r:r['seed']) for mode in ('ufls','rakshak')}
            result = {'magnitude':magnitude,'participation':participation,'seeds':args.seeds,'delta_definition':'Rakshak minus reference AUFLS','metrics':{}}
            for metric in metrics:
                values = [b[metric]-a[metric] for a,b in zip(paired['ufls'],paired['rakshak'])]
                mean=statistics.mean(values)
                half=2.093*statistics.stdev(values)/math.sqrt(len(values)) if len(values)>1 else 0
                result['metrics'][metric]={'reference_mean':statistics.mean(r[metric] for r in paired['ufls']), 'rakshak_mean':statistics.mean(r[metric] for r in paired['rakshak']), 'paired_mean_difference':mean,'paired_95_percent_t_interval':[mean-half,mean+half]}
            summaries.append(result)
    (root/'summary.json').write_text(json.dumps({'protocol':{'duration_s':270,'step_s':.05,'seeds':list(range(args.seeds)),'inventory':inventory,'interval':'paired Student t; 2.093 for planned 20 seeds; descriptive across modeled seeds, not field uncertainty'},'groups':summaries},indent=2))
    print('Saved paired_runs.csv and summary.json',flush=True)


if __name__ == '__main__':
    main()
