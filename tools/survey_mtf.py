"""Survey the unit library for Combat Lab tokens (INTEGRATION__COMBAT_LAB.md).
Usage: python -I tools/survey_mtf.py <folder with unzipped data/meks.zip>
Rough counts only (ammo lines leak into the weapon-zone tally; tonnage bins sum low)."""
import sys,os,re,collections as C
root=sys.argv[1]
cfg=C.Counter();ton=C.Counter();arm=C.Counter();zone=C.Counter();cls=C.Counter()
tech=C.Counter();jj=C.Counter();n=0;rear=0;nocockpit=0;omni=0
def klass(w):
    w=w.lower()
    if any(k in w for k in('lrm','srm','mrm','atm','mml','streak','rocket','narc','arrow')): return 'missile'
    if any(k in w for k in('laser','ppc','flamer')): return 'energy'
    if any(k in w for k in('ac','gauss','machine','mg','rifle','lb','ultra')): return 'ballistic'
    return 'other'
for d,_,fs in os.walk(root):
  for f in fs:
    if not f.endswith('.mtf'):continue
    L=open(os.path.join(d,f),errors='ignore').read().splitlines();n+=1
    cur=None;slots=C.defaultdict(list);inw=False
    for l in L:
        if l.startswith('Config:'):cfg[l[7:].strip()]+=1; omni+=('Omni' in l)
        elif l.lower().startswith('mass:'):ton[int(l[5:])//10*10]+=1
        elif l.startswith('TechBase:'):tech[l[9:].strip()]+=1
        elif l.startswith('Jump MP:'):jj[min(int(l[8:] or 0),8)]+=1
        elif l.startswith('Weapons:'):inw=True
        elif re.match(r'^(Left|Right|Front|Rear) (Arm|Leg):$|^(Head|Center Torso|Left Torso|Right Torso):$',l):cur=l[:-1];slots[cur];inw=False
        elif l.strip()=='':inw=False
        elif inw and ',' in l:
            w,loc=l.rsplit(',',1);zone[loc.replace('(R)','').strip()]+=1;cls[klass(w)]+=1
            rear+=('(R)' in loc)
        elif cur:slots[cur].append(l)
    for a in ('Left Arm','Right Arm'):
        s=' '.join(slots.get(a,[]))
        if not s and 'Left Arm' not in slots: continue
        arm['hand' if 'Hand Actuator' in s else 'lowerarm' if 'Lower Arm Actuator' in s else 'upper_only' if 'Upper Arm' in s else 'no_actuators']+=1
    nocockpit+=('Cockpit' not in ' '.join(slots.get('Head',[])))
print(n,'units')
for name,c in [('config',cfg),('tonnage',ton),('arm actuators',arm),('weapon zone',zone),('weapon class',cls),('techbase',tech),('jump MP',jj)]:
    print('\n',name,dict(c.most_common(14)))
print('\nrear-facing weapons',rear,'| omni',omni,'| head w/o cockpit',nocockpit)
