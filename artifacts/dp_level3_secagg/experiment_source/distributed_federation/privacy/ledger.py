"""Durable spend-before-send guard. Deleting/rolling back the ledger voids accounting.

Reservations count even if sending fails. A restart in the same run fails closed.
No private keys, masks, updates, or noise realizations are persisted here.
"""
import json
import sqlite3
from pathlib import Path

class Ledger:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=30)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS spends (run TEXT, round INTEGER, role TEXT, config TEXT, PRIMARY KEY(run,round,role))')
        self.db.commit()
    def reserve(self,run,round_id,role,config):
        try:
            with self.db:
                self.db.execute('INSERT INTO spends VALUES (?,?,?,?)',(run,round_id,role,json.dumps(config,sort_keys=True)))
        except sqlite3.IntegrityError as exc: raise ValueError('Already reserved; restart requires a new run_id and composed budget') from exc
    def entries(self):
        return [dict(run=r,round=t,role=k,config=json.loads(c)) for r,t,k,c in self.db.execute('SELECT * FROM spends')]
    def close(self): self.db.close()
