import json
import math
from .bootstrap import PROJECT
from .geometry import BearingGeometry


class Bearings:
    def __init__(self):
        p=PROJECT/'data/public_validation/metadata/bearing_frequency_catalog.json'
        self.rows=json.loads(p.read_text(encoding='utf-8'))['bearings'] if p.exists() else []
        self.by_id={r['id']:r for r in self.rows}

    def frequencies(self, id, rpm):
        if not id or not rpm:
            return {}
        if id not in self.by_id:
            raise ValueError('베어링 카탈로그에 없는 항목입니다.')
        if not math.isfinite(rpm) or rpm<=0:
            raise ValueError('RPM은 양수여야 합니다.')
        b=self.by_id[id]
        if 'orders' in b:
            return {k:float(v)*rpm/60 for k,v in b['orders'].items()}
        if 'hz_per_rpm' in b:
            return {k:float(v)*rpm for k,v in b['hz_per_rpm'].items()}
        return BearingGeometry(**b['geometry']).frequencies(rpm)

    def custom(self, values):
        g={k:float(values[k]) for k in ['rolling_elements','rolling_diameter','pitch_diameter','contact_angle_deg']}
        if any(isinstance(values[k],bool) for k in g) or not all(math.isfinite(v) for v in g.values()) or not g['rolling_elements'].is_integer():
            raise ValueError('베어링 내부 치수가 올바르지 않습니다.')
        g['rolling_elements']=int(g['rolling_elements'])
        BearingGeometry(**g).validate()
        name=str(values.get('name','사용자 베어링'))[:100]
        id='custom:'+name
        row={'id':id,'manufacturer':str(values.get('manufacturer','사용자'))[:100],'model':name,
             'dataset':'custom','geometry':g,'geometry_unit':values.get('geometry_unit','mm'),
             'note':'사용자 입력. 외륜 고정/내륜 회전/순수 구름 가정.'}
        self.by_id[id]=row
        self.rows=[r for r in self.rows if r['id']!=id]+[row]
        return row

