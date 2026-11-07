# Does the capacity index CI = 3600/run + 3600/fill cancel rain where raw run time does not?
import sys, pandas as pd
out = sys.argv[1]
r = pd.read_parquet(f'{out}/runs.parquet'); w = pd.read_parquet(f'{out}/rain.parquet')
rain = w.assign(day=w.t.dt.floor('D')).groupby(['site','day']).mm.sum()
for site in ['45078','45385','44371','47213']:
    s = r[r.site==site].sort_values('start').reset_index(drop=True)
    prev_end = s.end.shift().cummax()
    s['overlap'] = s.start < prev_end
    s['fill'] = (s.start - prev_end).dt.total_seconds()
    ok = ~s.overlap & s.fill.between(10, 6*3600) & s.dur.between(5, 3600)
    s['ci'] = (3600/s.dur + 3600/s.fill).where(ok)
    s['day'] = s.start.dt.floor('D')
    d = s.groupby(['pump','day']).agg(dur=('dur','median'), ci=('ci','median'), n=('ci','count'), ov=('overlap','mean')).reset_index()
    d['rain'] = d.day.map(rain.loc[int(site)]).fillna(0)
    d = d[d.n >= 10]
    print(f'\n== {site}  overlap share of all runs {s.overlap.mean():.1%}, valid-CI share {ok.mean():.1%}')
    for p, g in d.groupby('pump'):
        g22, g23 = g[g.day.dt.year==2022], g[g.day.dt.year==2023]
        wet, dry = g22[g22.rain>=10], g22[g22.rain==0]
        cv = lambda x: (x.quantile(.75)-x.quantile(.25))/x.median()
        print(f' P{p}: days22={len(g22)} rho(rain) dur={g22.dur.rank().corr(g22.rain.rank()):+.2f} ci={g22.ci.rank().corr(g22.rain.rank()):+.2f} | '
              f'wet/dry dur={wet.dur.median()/dry.dur.median():.2f} ci={wet.ci.median()/dry.ci.median():.2f} (wet n={len(wet)}) | '
              f'2023/2022 dur={g23.dur.median()/g22.dur.median():.2f} ci={g23.ci.median()/g22.ci.median():.2f} | IQR/med dur={cv(g22.dur):.2f} ci={cv(g22.ci):.2f}')
    if site == '44371':
        e = d[(d.pump==1) & d.day.between('2022-05-10','2022-06-12')][['day','dur','ci','n','rain']]
        print(e.to_string(index=False))
