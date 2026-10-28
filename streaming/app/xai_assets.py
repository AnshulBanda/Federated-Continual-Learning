"""Serve the shared XAI renderer and component-only, scoped styles."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / 'xai/static'
EXCLUDED = ('header-inner','layout','panel','filters','case-table','case','chip','pager','tablewrap','counts','legend','detail','empty','loading','status')


def scoped_css(source):
    """Scope approved component rules; keep the AML shell's base elements/styles."""
    source=re.sub(r'/\*.*?\*/','',source,flags=re.S)
    def rules(text):
        result=[];position=0
        while position<len(text):
            opening=text.find('{',position)
            if opening<0:break
            selector=text[position:opening].strip();depth=1;end=opening+1
            while end<len(text) and depth:
                depth+=(text[end]=='{')-(text[end]=='}');end+=1
            content=text[opening+1:end-1];position=end
            if selector.startswith('@media'):
                children=rules(content)
                if children:result.append(selector+'{'+children+'}')
                continue
            selectors=[]
            for part in selector.split(','):
                part=part.strip()
                match=re.match(r'\.([\w-]+)',part)
                if match and match[1] not in EXCLUDED:
                    selectors.append('.xai-investigator '+part)
            if selectors:result.append(','.join(selectors)+'{'+content+'}')
        return '\n'.join(result)
    return '.xai-investigator{--surface:#fff;--soft:#fafcfc;--up:#9b6019;--down:#27846c;min-width:0}\n'+rules(source)


def asset(name):
    if name=='replay_investigator.js':
        return (STATIC.parents[1]/'streaming/web/replay_investigator.js').read_bytes(),'text/javascript; charset=utf-8'
    if name not in ('dashboard.js','explanation_summary.js','bank_display.js','dashboard.css'):
        return None
    path=STATIC/name
    if name.endswith('.css'):
        return scoped_css(path.read_text(encoding='utf-8')).encode(),'text/css; charset=utf-8'
    return path.read_bytes(),'text/javascript; charset=utf-8'
