import unittest,tempfile,json,threading,urllib.request,re
from pathlib import Path
from streaming.app.monitoring import Monitoring
from streaming.app.local_training import write_json,read_json,now
from streaming.app.results import research_results
from streaming.app.dashboard import server
class TabTests(unittest.TestCase):
 def test_research_all_methods_and_splits(self):
  rows=research_results();self.assertEqual(len(rows),54)
  self.assertEqual({r['method'] for r in rows},{'local','cl','corrected_fedavg'})
  self.assertEqual({r['split'] for r in rows},{'validation','testing'})
 def test_restart_and_bank_isolation(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'monitoring'/'a'/'job.json'
   write_json(path,dict(id='a',bank='Key_Bank',status='Running',started=now()))
   m=Monitoring(tmp);self.assertEqual(m.status('Key_Bank')['jobs'][0]['status'],'Interrupted')
   self.assertEqual(m.status('Wells_Fargo')['jobs'],[])
   with self.assertRaises(ValueError):m.rows('../a','Key_Bank')
   with self.assertRaises(ValueError):m.cancel('a','Wells_Fargo')
   m.cancel('a','Key_Bank');self.assertFalse((path.parent/'cancel.json').exists())
 def test_http_routes_and_csrf(self):
  with tempfile.TemporaryDirectory() as tmp:
   app=server(tmp,0);thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
   base='http://127.0.0.1:'+str(app.server_port)
   try:
    html=urllib.request.urlopen(base).read().decode();self.assertIn('id="monitoringtab"',html);self.assertIn('id="resultstab"',html)
    for route in ('/api/results','/api/monitoring'):
     data=json.load(urllib.request.urlopen(base+route));self.assertIsInstance(data,dict)
    request=urllib.request.Request(base+'/api/monitoring/start',data=b'{}',headers={'Content-Type':'application/json'})
    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
    self.assertEqual(error.exception.code,403)
   finally:app.shutdown();app.server_close();thread.join()
if __name__=='__main__':unittest.main()
