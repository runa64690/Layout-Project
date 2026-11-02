"""Reproducible scenario comparison; writes inputs and outputs, not just scores.

Run with the repository's Python environment from any directory.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from api_contract import LayoutDTO, evaluate_payload, optimize_payload
from mcmc_solver import MCMCSolver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=900)
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/safety-benchmark.json')
    args = parser.parse_args()
    coordinates = {'shelf':(10,10), 'bed':(3,8), 'table':(8,3),
                   'tv_unit':(12,3), 'chair':(6,3), 'ceiling_light':(8,3)}
    base = {'room':{'grid_w':16,'grid_h':16,
        'doors':[{'key':'door','wall':'LEFT','offset':5,'length':2}],
        'windows':[{'key':'window','wall':'TOP','offset':5,'length':2}]},
        'placements':[{'key':k,'gx':x,'gy':y,'rotation':0,'placed':True} for k,(x,y) in coordinates.items()]}
    rows = []
    for case in ('placed', 'empty', 'crowded', 'fixed_bed'):
        layout = deepcopy(base)
        if case in ('empty','crowded'):
            for p in layout['placements']:
                p.update(gx=0,gy=0,placed=False)
        if case == 'crowded':
            layout['room'].update(grid_w=8,grid_h=8)
        initial = evaluate_payload(LayoutDTO.model_validate(layout)).model_dump() if case in ('placed','fixed_bed') else None
        for seed in (0,1,42):
            request = {'layout':layout,'rng_seed':seed,'sample_count':args.steps,
                       'burn_in':min(250,args.steps//3),'sample_stride':15,'candidate_count':3,
                       'fixed_keys':['bed'] if case=='fixed_bed' else []}
            start = time.perf_counter()
            candidates = optimize_payload(request)
            elapsed = time.perf_counter()-start
            domain = [LayoutDTO.model_validate({'room':layout['room'],'placements':c['placements']}).to_domain() for c in candidates]
            distances = [MCMCSolver()._layout_distance(domain[i][0],domain[i][1],domain[j][1])
                         for i in range(len(domain)) for j in range(i+1,len(domain))]
            row = {'case':case,'seed':seed,'elapsed_seconds':round(elapsed,3),
                   'candidate_count':len(candidates),
                   'met_count':sum(c['safety']['status']=='met' for c in candidates),
                   'best_findings':candidates[0]['safety']['violation_count'] if candidates else None,
                   'mean_pair_distance':statistics.mean(distances) if distances else 0,
                   'request':request,'initial':initial,'candidates':candidates}
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k not in ('request','initial','candidates')}),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'evaluation_version':2,'steps':args.steps,'runs':rows},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
