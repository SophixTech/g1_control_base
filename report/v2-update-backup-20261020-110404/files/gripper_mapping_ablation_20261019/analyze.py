"""Offline quartic removal: unchanged recorded inputs/timing, no robot/model execution."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
SRC=Path('/home/bjtc/Sophix/g1-open-rail/report/gripper_audit_20261019')
OUT=Path(__file__).resolve().parent

def transitions(v,t):
 state=None; ev=[]
 for i,z in enumerate(v):
  new=0 if z<=.2 else 1 if z>=.8 else state
  if state is not None and new is not None and state!=new:ev.append((i,new))
  state=new
 return ev

def runs(mask):
 edges=np.diff(np.r_[False,mask,False].astype(int));return list(zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)))
rows=[];roundtrips=[];thresholds=[];example=None
for path in sorted(SRC.glob('*_commands.csv')):
 d=pd.read_csv(path);session=path.name.removesuffix('_commands.csv');t=d.t.to_numpy();q=d.q.to_numpy();x=np.clip(d.input_target.to_numpy(),0,1)
 assert np.max(abs(q-x**4/(x**4+(1-x)**4)))<1e-12
 blocks=np.cumsum(np.r_[False,np.diff(t)>.2]);valid=np.r_[False,np.diff(t)<=.2]
 row=dict(session=session,samples=len(t),closed_before=int(sum(q>=.8)),closed_to_mid=int(sum((q>=.8)&(x<.8))),open_before=int(sum(q<=.2)),open_to_mid=int(sum((q<=.2)&(x>.2))),mid_before=int(sum((q>.2)&(q<.8))),mid_after=int(sum((x>.2)&(x<.8))),switches_before=0,switches_after=0,short_intervals_before=0,short_intervals_after=0,closed_runs=0,closed_runs_affected=0,closed_runs_never_reach_08=0)
 for thr in [.8,.9,.95,.99,1.]:thresholds.append(dict(session=session,threshold=thr,before=int(sum(q>=thr)),after=int(sum(x>=thr)),lost=int(sum((q>=thr)&(x<thr)))))
 for b in np.unique(blocks):
  ix=np.flatnonzero(blocks==b);qq=q[ix];xx=x[ix];tt=t[ix]
  old=transitions(qq,tt);new=transitions(xx,tt)
  row['switches_before']+=len(old);row['switches_after']+=len(new)
  row['short_intervals_before']+=sum(tt[j[0]]-tt[i[0]]<.5 for i,j in zip(old[:-1],old[1:]));row['short_intervals_after']+=sum(tt[j[0]]-tt[i[0]]<.5 for i,j in zip(new[:-1],new[1:]))
  for l,r in runs(qq>=.8):
   row['closed_runs']+=1;row['closed_runs_affected']+=int(np.any(xx[l:r]<.8));row['closed_runs_never_reach_08']+=int(np.max(xx[l:r])<.8)
  # Consecutive close -> open -> close transition triplets; inclusive aligned window.
  for a,bb,c in zip(old[:-2],old[1:-1],old[2:]):
   if [a[1],bb[1],c[1]]!=[1,0,1]:continue
   l=a[0];r=c[0]+1;z=xx[l:r];ez=transitions(z,tt[l:r]);has_return=any(u[1]==0 and v[1]==1 for u,v in zip(ez[:-1],ez[1:]))
   if np.min(z)>=.8:status='kept_closed'
   elif has_return:status='still_open_close'
   elif np.min(z)>.2 and np.max(z)>=.8:status='dip_to_middle_only'
   elif np.max(z)<.8:status='never_reaches_closed'
   else:status='no_full_roundtrip_within_original_window'
   roundtrips.append(dict(session=session,start_s=float(tt[l]),open_s=float(tt[bb[0]]),end_s=float(tt[r-1]),open_duration_s=float(tt[c[0]]-tt[bb[0]]),status=status,min_after=float(z.min()),max_after=float(z.max())))
  if session.startswith('20261018_144451'):example=(t,q,x)
 row['jumps_before']=int(sum((np.r_[0,abs(np.diff(q))]>=.25)&valid));row['jumps_after']=int(sum((np.r_[0,abs(np.diff(x))]>=.25)&valid))
 rows.append(row)
pd.DataFrame(rows).to_csv(OUT/'sessions.csv',index=False);pd.DataFrame(thresholds).to_csv(OUT/'closure_thresholds.csv',index=False);pd.DataFrame(roundtrips).to_csv(OUT/'close_open_close_events.csv',index=False)
total=pd.DataFrame(rows).drop(columns='session').sum().astype(int).to_dict();total['event_categories']=pd.DataFrame(roundtrips).status.value_counts().to_dict();total['rapid_open_under_05s_categories']=pd.DataFrame(roundtrips).query('open_duration_s < .5').status.value_counts().to_dict()
(OUT/'summary.json').write_text(json.dumps(total,indent=2));print(json.dumps(total,indent=2));print(pd.DataFrame(rows).to_string(index=False))
fig,axs=plt.subplots(2,1,figsize=(12,7));df=pd.DataFrame(rows);pos=np.arange(len(df));axs[0].bar(pos-.18,df.switches_before,width=.36,label='Quartic');axs[0].bar(pos+.18,df.switches_after,width=.36,label='Identity');axs[0].set_xticks(pos,[s[9:15] for s in df.session]);axs[0].set_ylabel('Hysteretic state transitions');axs[0].legend()
t,q,x=example;sel=(t>=10)&(t<=25);axs[1].plot(t[sel],q[sel],label='Quartic');axs[1].plot(t[sel],x[sel],label='Identity');axs[1].axhline(.8,color='gray',ls='--');axs[1].axhline(.2,color='gray',ls='--');axs[1].set(xlabel='Time (s)',ylabel='Target (0=open,1=closed)');axs[1].legend();fig.tight_layout();fig.savefig(OUT/'comparison.png',dpi=150)
