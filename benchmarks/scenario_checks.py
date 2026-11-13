import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from simulation import ScenarioRequest,compare_modes
CASES={'normal':{'generation_loss':0},'demand_surge':{'disturbance':'demand_surge'},'solar_surplus':{'disturbance':'solar_surplus','generation_loss':.12},'feeder_fault':{'disturbance':'feeder_fault'},'backup_exhaustion':{'disturbance':'feeder_fault','clinical_backup_minutes':.25,'t_recover':90},'restoration':{},'low_inertia':{'grid_inertia_h':3},'high_inertia':{'grid_inertia_h':8},'trigger_49_5':{'shed_threshold':49.5},'trigger_49_8':{'shed_threshold':49.8}}
def run(item):
 name,fields=item
 result=compare_modes(ScenarioRequest(**fields))
 for row in result:row.pop('trace')
 return name,result
if __name__=='__main__':
 with ProcessPoolExecutor(max_workers=6) as pool: data=dict(pool.map(run,CASES.items()))
 Path('benchmarks/results/scenario_checks.json').write_text(json.dumps(data,indent=2))
 print('Completed',len(CASES)*4,'scenario and sensitivity runs')
