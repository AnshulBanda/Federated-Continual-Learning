"""Read saved research metrics; never rerun or tune the frozen test."""
from pathlib import Path
from .overview import REPO
from .local_training import read_json

def research_results(repo=REPO):
    rows=[]
    for method in ('local','cl','corrected_fedavg'):
        for path in sorted((Path(repo)/'artifacts/final_evaluation'/method).glob('seed_*/metrics.json')):
            data=read_json(path,{})
            for row in (data if isinstance(data,list) else data.get('per_bank',[])):
                for split in ('validation','testing'):
                    if isinstance(row.get(split),dict):
                        rows.append(dict(method=method,seed=path.parent.name,bank=row.get('bank'),split=split,metrics=row[split],source=str(path.relative_to(repo))))
    return rows
