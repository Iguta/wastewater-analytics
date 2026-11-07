# Which free public signals separate Bloomington SSO cause classes from ordinary days? (lift vs base rate)
import json, re, sys, pandas as pd
inc = sys.argv[1]
sso = pd.DataFrame(json.load(open(f'{inc}/sso.json')))
sso['day'] = pd.to_datetime(sso.start_date).dt.floor('D')
w = json.load(open(f'{inc}/blm_weather.json'))['daily']
w = pd.DataFrame(w).assign(day=lambda d: pd.to_datetime(d.time)).set_index('day')
ev = sso.event.fillna('').str.lower()
cls = {
  'power':     ev.str.contains('power|electric|outage|lightning'),
  'blockage':  ev.str.contains('grease|block|root|debris|rag|wipe|obstruct'),
  'equipment': ev.str.contains('equip|mechanic|pump|malfunction|fail') & ~ev.str.contains('power|electric|outage|lightning'),
  'weather':   ev.str.contains('precip|rain|storm|snow|weather|inflow|infiltration'),
}
md = w.index.month*100 + w.index.day
feats = {
  'gust>=45mph':     w.wind_gusts_10m_max >= 45,
  'rain>=1in':       w.precipitation_sum >= 1,
  'rain>=0.5in':     w.precipitation_sum >= 0.5,
  'tmin<=-7C(20F)':  w.temperature_2m_min <= -7,
  'tmax>=32C(90F)':  w.temperature_2m_max >= 32,
  'holiday Nov20-Jan5': pd.Series((md >= 1120) | (md <= 105), index=w.index),
}
print('base days', len(w), {k: f'{v.mean():.1%}' for k, v in feats.items()})
for name, m in cls.items():
    days = pd.DatetimeIndex(sso[m & (sso.day >= w.index[0]) & (sso.day <= w.index[-1])].day.unique())
    row = {k: f'{v.reindex(days).mean():.0%} (x{v.reindex(days).mean()/v.mean():.1f})' for k, v in feats.items()}
    print(f'{name:9s} n_days={len(days):3d}', row)
