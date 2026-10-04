#!/usr/bin/env python3
"""Generate an offline, self-contained comparison report. Never imports the SDK."""

import argparse
import bisect
import csv
import html
import json
import math
from pathlib import Path
import statistics


def read_events(directory):
    events, warnings = [], []
    for name in ('client', 'robot'):
        path = directory / f'{name}.jsonl'
        if not path.exists():
            warnings.append(f'Missing {path.name}')
            continue
        ended = False
        for number, line in enumerate(path.read_text().splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f'{path.name}:{number}: incomplete or invalid JSON')
                continue
            events.append(row)
            if row['event'] == 'stream_end':
                ended = True
                if row['dropped']:
                    warnings.append(f'{name}: {row["dropped"]} dropped records')
        if not ended:
            warnings.append(f'{name}: no clean end marker; capture may still be running or incomplete')
    return sorted(events, key=lambda row: row['mono_ns']), warnings


def model_reference(model, offset):
    """Linear reference between original model samples, NOT the cubic fitted target."""
    if model is None or offset is None or not model['q']:
        return None
    index = min(max(offset / model['raw_period_s'], 0), len(model['q']) - 1)
    left = int(index)
    right = min(left + 1, len(model['q']) - 1)
    return model['q'][left] + (model['q'][right] - model['q'][left]) * (index - left)


def estimate_motion_onsets(events, feedback, commands, threshold):
    """Detect sustained feedback displacement after a stable baseline, not motor ACK."""
    result = []
    stops = [e['mono_ns'] for e in events if e['event'] in ('control_stop', 'control_start')]
    for start in (e for e in events if e['event'] == 'control_start'):
        begin = start['mono_ns']
        end = min((t for t in stops if t > begin), default=math.inf)
        sent = next((c for c in commands if begin <= c['send_start_ns'] < end), None)
        entry = dict(control_start_ns=begin, first_send_ns=None, status='no successful SDK command')
        if sent:
            t = sent['send_start_ns']
            entry['first_send_ns'] = t
            before = [f for f in feedback if t - 250_000_000 <= f['mono_ns'] < t]
            if len(before) < 3 or max(f['q'] for f in before) - min(f['q'] for f in before) > threshold / 2:
                entry['status'] = 'unknown: insufficient or moving pre-command baseline'
            else:
                baseline = statistics.median(f['q'] for f in before)
                last_still = before[-1]['mono_ns']
                moving = []
                entry['status'] = 'no sustained motion above threshold detected'
                for f in feedback:
                    if not t <= f['mono_ns'] < end:
                        continue
                    if abs(f['q'] - baseline) >= threshold:
                        moving.append(f)
                        if len(moving) == 3:
                            entry.update(status='estimated from three distinct feedback samples',
                                         last_still_seen_ns=last_still,
                                         first_moving_seen_ns=moving[0]['mono_ns'],
                                         confirmed_seen_ns=f['mono_ns'],
                                         first_moving_device_stamp_ns=moving[0]['device_stamp_ns'])
                            break
                    else:
                        last_still = f['mono_ns']
                        moving = []
        result.append(entry)
    return result


def analyze(events, threshold=0.002):
    models = {e['chunk_id']: e for e in events if e['event'] == 'model_chunk' and e.get('chunk_id')}
    submits = {e['command_id']: e for e in events if e['event'] == 'command_submit'}
    commands = sorted((e for e in events if e['event'] == 'sdk_command'), key=lambda e: e['send_start_ns'])
    feedback, stamps = [], set()
    for e in events:
        if e['event'] == 'feedback' and e['device_stamp_ns'] not in stamps:
            feedback.append(e)
            stamps.add(e['device_stamp_ns'])
    feedback_times = [e['mono_ns'] for e in feedback]
    rows = []
    for command in commands:
        submit = submits.get(command.get('command_id'), {})
        t = command['send_start_ns']
        reference = model_reference(models.get(command.get('chunk_id')), command.get('planned_offset_s'))
        index = bisect.bisect_right(feedback_times, t) - 1
        observed = feedback[index] if index >= 0 else None
        row = dict(command_id=command.get('command_id'), chunk_id=command.get('chunk_id'),
                   source=command.get('source', 'policy'),
                   submit_ns=command.get('submit_ns'), send_start_ns=t,
                   send_end_ns=command['send_end_ns'],
                   sdk_call_ms=(command['send_end_ns'] - t) / 1e6,
                   queue_delay_ms=(t - command['submit_ns']) / 1e6 if command.get('submit_ns') else None,
                   planned_offset_s=command.get('planned_offset_s'), fitted_index=command.get('fitted_index'),
                   model_linear_reference_rad=reference, fitted_target_rad=submit.get('q'),
                   planned_velocity_rad_s=submit.get('planned_velocity'),
                   planned_acceleration_rad_s2=submit.get('planned_acceleration'),
                   sdk_target_rad=command['q'],
                   fitted_minus_model_rad=submit['q'] - reference if 'q' in submit and reference is not None else None,
                   sdk_minus_fitted_rad=command['q'] - submit['q'] if 'q' in submit else None,
                   last_feedback_rad=observed['q'] if observed else None,
                   feedback_seen_ns=observed['mono_ns'] if observed else None,
                   device_feedback_stamp_ns=observed['device_stamp_ns'] if observed else None,
                   feedback_age_at_send_ms=(t - observed['mono_ns']) / 1e6 if observed else None)
        rows.append(row)
    confirmed = {c.get('command_id') for c in commands}
    discarded = {e.get('command_id') for e in events if e['event'] == 'command_discard'}
    failed = {e.get('command_id') for e in events if e['event'] == 'sdk_error'}
    control_failed = {e.get('command_id') for e in events if e['event'] == 'control_error'}
    intervals = [(b['send_start_ns'] - a['send_start_ns']) / 1e6 for a, b in zip(commands, commands[1:])]
    onsets = estimate_motion_onsets(events, feedback, commands, threshold)
    summary = dict(joint=next((e['joint'] for e in events if e['event'] == 'stream_start'), None),
                   model_chunks=len(models), submitted=len(submits), sdk_calls_returned=len(commands),
                   sdk_errors=sum(e['event'] == 'sdk_error' for e in events), explicitly_discarded=len(discarded),
                   worker_control_errors=len(control_failed),
                   submitted_without_terminal_record=len(set(submits) - confirmed - discarded - failed - control_failed),
                   unique_feedback_samples=len(feedback),
                   median_send_interval_ms=statistics.median(intervals) if intervals else None,
                   onset_threshold_rad=threshold, motion_onsets=onsets,
                   interpretation='SDK return is not device acceptance/execution. Feedback uses PC observation time; device stamps are not clock-aligned.')
    return dict(models=list(models.values()), submits=list(submits.values()), commands=commands,
                settings=[e for e in events if e['event'] in ('speed_applied', 'control_period_applied')],
                feedback=feedback, rows=rows, summary=summary)


def write_csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_report(directory, result, warnings):
    bundle = Path(__file__).resolve().parents[1] / 'visual/vlib/chart.js'
    chart_js = bundle.read_text().replace('</script', '<\\/script')
    events = result['commands'] + result['feedback'] + result['models']
    result['origin_ns'] = min((e['mono_ns'] for e in events), default=0)
    result['warnings'] = warnings
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>关节模型 / 下发 / 反馈对比</title>
<style>body{font:15px system-ui;margin:24px;background:#fafafa;color:#222}section{background:white;padding:16px;margin:16px 0;border:1px solid #ddd} .plot{height:340px}pre{white-space:pre-wrap}select,input{margin:8px}label{display:inline-block}</style>
<h1>关节模型 / 下发 / 反馈对比</h1><p>__DIRECTORY__</p>
<p>横轴统一为 PC 单调时钟。SDK 调用返回不代表电机收到或开始执行。反馈曲线按 PC 读到反馈的时刻绘制；设备原始采样时间戳保存在 CSV 中，未假设与 PC 同步。</p>
<p>模型虚线是原始预测点的线性连接；目标差值使用同一块、同一 planned_offset 的线性参考，不等于模型“错误”。规划插值和块间衔接本来就可能改变目标。Reset/手动移动也记录 SDK 目标，但没有模型块对应关系。</p>
<label>预测块 <select id="chunk"></select></label><label>起始秒 <input id="lo" type="number" value="0" step="0.1"></label><label>结束秒 <input id="hi" type="number" step="0.1"></label><button id="draw">更新范围</button>
<section><h2>位置（rad）</h2><div class="plot"><canvas id="position"></canvas></div></section>
<section><h2>目标处理差异（rad）</h2><div class="plot"><canvas id="difference"></canvas></div></section>
<section><h2>相邻样本差分速度（rad/s）</h2><p>下发曲线是命令目标变化率；反馈曲线按设备采样间隔求导、按 PC 观察时刻定位。噪声会放大，均不作为控制限值。</p><div class="plot"><canvas id="velocity"></canvas></div></section>
<section><h2>时序、开始运动估计和完整性</h2><pre id="summary"></pre></section>
<script>__CHART__</script><script>
const D=__DATA__, origin=D.origin_ns, sec=t=>(t-origin)/1e9;
const pick=document.getElementById('chunk');
const option=document.createElement('option'); option.value='';option.textContent='不叠加原始预测';pick.append(option);
D.models.forEach(m=>{const o=document.createElement('option');o.value=m.chunk_id;o.textContent=m.chunk_id+' · speed='+m.speed;pick.append(o)});
if(D.commands.length)pick.value=D.commands[D.commands.length-1].chunk_id;
document.getElementById('hi').value=D.commands.concat(D.feedback).reduce((v,e)=>Math.max(v,sec(e.send_end_ns||e.mono_ns)),1).toFixed(2);
const line=(label,data,color,dash=[])=>({label,data,borderColor:color,borderDash:dash,borderWidth:1.4,pointRadius:0,tension:0,spanGaps:false});
const charts=[];
function derivative(rows,time,device=false){const out=[];for(let i=1;i<rows.length;i++){const a=rows[i-1],b=rows[i],dt=(time(b)-time(a))/1e9;if(dt>0)out.push({x:sec(device?b.mono_ns:time(b)),y:(b.q-a.q)/dt})}return out}
function draw(){charts.forEach(c=>c.destroy());charts.length=0;
 const lo=Number(document.getElementById('lo').value),hi=Number(document.getElementById('hi').value);
 const m=D.models.find(m=>m.chunk_id===pick.value);
 const pos=[line('客户端提交目标',D.submits.map(c=>({x:sec(c.submit_ns),y:c.q})),'#e8a127'),line('SDK 实际调用目标',D.commands.map(c=>({x:sec(c.send_start_ns),y:c.q})),'#2463d4'),line('真机关节反馈',D.feedback.map(f=>({x:sec(f.mono_ns),y:f.q})),'#168b59')];
 if(m)pos.unshift(line('模型原始预测（所选块）',m.q.map((q,i)=>({x:sec(m.observation_pc_s*1e9)+i*m.raw_period_s,y:q})),'#a044c4',[5,4]));
 const visible=pos.flatMap(s=>s.data.filter(p=>p.x>=lo&&p.x<=hi));
 const bounds=visible.reduce((a,p)=>[Math.min(a[0],p.y),Math.max(a[1],p.y)],[Infinity,-Infinity]);
 if(visible.length){const low=bounds[0]-.01,high=bounds[1]+.01;
  for(const [key,label,color] of [['control_start_ns','Control 开启','#888'],['first_send_ns','首次 SDK 下发','#d46c24'],['first_moving_seen_ns','首次反馈运动（估计）','#168b59']]){
   const points=[];D.summary.motion_onsets.forEach(o=>{if(o[key]!=null){const x=sec(o[key]);points.push({x,y:low},{x,y:high},{x,y:null})}});
   pos.push(line(label,points,color,[2,4]));
  }
 }
 const diff=[line('提交目标 − 模型线性参考',D.rows.map(r=>({x:sec(r.send_start_ns),y:r.fitted_minus_model_rad})),'#a044c4'),line('SDK目标 − 提交目标',D.rows.map(r=>({x:sec(r.send_start_ns),y:r.sdk_minus_fitted_rad})),'#2463d4')];
 const vel=[line('命令目标变化率',derivative(D.commands,c=>c.send_start_ns),'#2463d4'),line('实测关节差分速度',derivative(D.feedback,f=>f.device_stamp_ns,true),'#168b59')];
 for(const [id,sets] of [['position',pos],['difference',diff],['velocity',vel]])charts.push(new Chart(document.getElementById(id),{type:'line',data:{datasets:sets},options:{animation:false,maintainAspectRatio:false,parsing:false,interaction:{mode:'nearest',intersect:false},scales:{x:{type:'linear',min:lo,max:hi,title:{display:true,text:'PC 相对时间 / 秒'}}}}}));
}
const onsets=D.summary.motion_onsets.map(o=>{const x={...o};for(const k of ['control_start_ns','first_send_ns','last_still_seen_ns','first_moving_seen_ns','confirmed_seen_ns'])if(x[k]!=null)x[k.replace('_ns','_s')]=sec(x[k]);return x});
document.getElementById('summary').textContent=JSON.stringify({...D.summary,motion_onsets:onsets,settings:D.settings,warnings:D.warnings},null,2);
pick.onchange=draw;document.getElementById('draw').onclick=draw;draw();
</script></html>'''
    rendered = template.replace('__DIRECTORY__', html.escape(str(directory)))
    return rendered.replace('__CHART__', chart_js).replace('__DATA__', payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--motion-threshold-rad', type=float, default=0.002)
    args = parser.parse_args()
    if not math.isfinite(args.motion_threshold_rad) or args.motion_threshold_rad <= 0:
        parser.error('motion threshold must be positive and finite')
    events, warnings = read_events(args.session)
    if not events:
        parser.error('No trace events found')
    result = analyze(events, args.motion_threshold_rad)
    write_csv(args.session / 'commands.csv', result['rows'])
    write_csv(args.session / 'feedback.csv', result['feedback'])
    (args.session / 'summary.json').write_text(json.dumps(dict(**result['summary'], warnings=warnings), indent=2))
    report = args.session / 'report.html'
    report.write_text(render_report(args.session, result, warnings))
    print(report.resolve())
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
    for warning in warnings:
        print('WARNING:', warning)


if __name__ == '__main__':
    main()
