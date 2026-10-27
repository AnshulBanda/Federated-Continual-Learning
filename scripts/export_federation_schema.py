"""Export a JSON-only demo encoder contract from the public simulated reference data."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.gnn.causal_temporal_graphsage import BANKS, fit_shared_feature_encoders

def spec(encoder):
    out={'numeric':[],'categorical':[]}
    for name, pipeline, columns in encoder.transformer.transformers_:
        if name=='remainder':continue
        if name=='numeric':
            for index,column in enumerate(columns):
                out['numeric'].append(dict(name=column,median=float(pipeline['impute'].statistics_[index]),mean=float(pipeline['scale'].mean_[index]),scale=float(pipeline['scale'].scale_[index])))
        else:
            def plain(value):return value.item() if hasattr(value,'item') else value
            for index,column in enumerate(columns):
                out['categorical'].append(dict(name=column,fill=plain(pipeline['impute'].statistics_[index]),categories=[plain(v) for v in pipeline['onehot'].categories_[index]]))
    return out

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/final_temporal_dataset')
    parser.add_argument('--output',type=Path,default=ROOT/'distributed_federation/feature_schema.json')
    args=parser.parse_args()
    nodes,edges=fit_shared_feature_encoders(args.dataset,BANKS)
    def width(value):return len(value['numeric'])+sum(len(c['categories']) for c in value['categorical'])
    n,e=spec(nodes),spec(edges)
    result=dict(format=1,source='Fixed synthetic AML reference training data; not fit on participant data at runtime',banks=list(BANKS),node_columns=nodes.columns,edge_columns=edges.columns,nodes=n,edges=e,node_feature_count=width(n),edge_feature_count=width(e))
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('Exported public demo feature contract:',args.output)
if __name__=='__main__':main()
