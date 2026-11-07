"""Write a read-only Dragonfly Perspective project (SCADA-overlay layout) into an Ignition 8.3 data/projects folder.

Usage: python3 ignition/make_project.py /usr/local/bin/ignition/data/projects [--force] [--api URL]   (then restart the gateway)
Open:  http://localhost:8088/data/perspective/client/Dragonfly

shortcut: the view's bindings call the REST API directly (system.net.httpGet), not the §10.8 gateway timer that
writes memory tags; switch the custom.a binding to the [default]Dragonfly tags once that path is running.
Read-only either way: it only GETs /api/assess and /api/evidence and writes no tags.
"""
import argparse, json, shutil
from pathlib import Path

ap = argparse.ArgumentParser(description="Write the Dragonfly Perspective project into an Ignition data/projects folder.")
ap.add_argument("projects_dir", help="for example /usr/local/bin/ignition/data/projects")
ap.add_argument("--api", default="http://127.0.0.1:8000", help="Dragonfly API base (Docker gateway: http://host.docker.internal:8000)")
ap.add_argument("--force", action="store_true", help="replace an existing Dragonfly project, including Designer edits")
args = ap.parse_args()
root = Path(args.projects_dir) / "Dragonfly"
API = args.api.rstrip("/")
if root.exists() and not args.force:
    raise SystemExit("%s exists; rerun with --force to replace it (Designer edits will be lost)" % root)
if root.exists():
    shutil.rmtree(root)
TS = "2026-11-07T21:30:00Z"
INK, MUTED, PANEL, LINE, ADD, ADD_LIGHT = "#1B1F23", "#4A5560", "#F4F5F6", "#B8BEC4", "#2D4A6B", "#9CC0F0"
WORDS = ("case({v}, 'INVESTIGATE', 'Investigate: inspect this pump', 'WATCH', 'Watch: capacity is dropping', "
         "'INSUFFICIENT_EVIDENCE', 'Not enough data', 'SOURCE_OFFLINE', 'Source offline', 'NORMAL', 'Normal', {v})")
STATUS_BG = ("case({v}, 'INVESTIGATE', '#B42318', 'WATCH', '#B54708', 'SOURCE_OFFLINE', '#3B434B', "
             "'INSUFFICIENT_EVIDENCE', '#6B7280', '#8A939B')")


def resource(files):
    return {"scope": "G", "version": 1, "restricted": False, "overridable": True, "files": files,
            "attributes": {"lastModification": {"actor": "dragonfly", "timestamp": TS}}}


def expr(e, transform=None):
    b = {"type": "expr", "config": {"expression": e}}
    if transform:
        b["transforms"] = [{"type": "script", "code": transform}]
    return {"binding": b}


def prop(path, transform=None, bidirectional=False):
    b = {"type": "property", "config": {"path": path, "bidirectional": bidirectional}}
    if transform:
        b["transforms"] = [{"type": "script", "code": transform}]
    return {"binding": b}


def label(name, text="", style=None, cfg=None, grow=0):
    n = {"type": "ia.display.label", "meta": {"name": name}, "position": {"shrink": 0, "grow": grow},
         "props": {"text": text, "style": {"color": INK, **(style or {})}, "textStyle": {"whiteSpace": "normal"}}}
    if cfg:
        n["propConfig"] = cfg
    return n


def flex(name, children, direction="column", style=None, basis="auto", grow=0, **props):
    return {"type": "ia.container.flex", "meta": {"name": name}, "position": {"basis": basis, "grow": grow, "shrink": 0},
            "props": {"direction": direction, "style": style or {}, **props}, "children": children}


def panel(name, title, sub, children, dashed=False, basis="auto", grow=0):
    border = ("2px dashed " + ADD) if dashed else ("1px solid " + LINE)
    return flex(name, [
        flex(name + "Head", [label("T", title, {"fontWeight": "600", "fontSize": "16px"}),
                             label("S", sub, {"fontSize": "13px", "color": MUTED})],
             style={"padding": "12px 20px", "borderBottom": ("1px dashed " + ADD) if dashed else ("1px solid " + LINE)}),
        flex(name + "Body", children, style={"padding": "14px 20px", "gap": "10px"}),
    ], style={"backgroundColor": PANEL, "border": border}, basis=basis, grow=grow)


def repeater(name, view_path, transform, source):
    return {"type": "ia.display.flex-repeater", "meta": {"name": name}, "position": {"shrink": 0},
            "props": {"path": view_path, "direction": "column", "elementPosition": {"basis": "165px", "shrink": 0, "grow": 0},
                      "style": {"gap": "10px"}, "instances": []},
            "propConfig": {"props.instances": prop(source, transform)}}


def view_doc(rootnode, params=None, custom=None, prop_config=None, size=(900, 1360)):
    pc = {"params." + k: {"paramDirection": "input", "persistent": True} for k in (params or {})}
    pc.update(prop_config or {})
    return {"custom": custom or {}, "params": params or {}, "propConfig": pc,
            "props": {"defaultSize": {"height": size[0], "width": size[1]}}, "root": rootnode}


FETCH = (
    "\timport urllib\n"
    "\tst, asof, sc = value.split('|')[0], value.split('|')[1], value.split('|')[2]\n"
    "\turl = '%s/api/assess?station_id=' + urllib.quote(st) + '&as_of_utc=' + urllib.quote(asof)\n"
    "\tif sc:\n"
    "\t\turl += '&scenario_id=' + urllib.quote(sc)\n"
    "\ttry:\n"
    "\t\treturn system.util.jsonDecode(system.net.httpGet(url, 5000, 15000))\n"
    "\texcept Exception as e:\n"
    "\t\treturn {'error': 'Dragonfly API not reachable (' + str(e) + ')', 'pumps': [], 'queue': [], 'safety': []}"
) % API

PUMPS = (
    "\tout = []\n"
    "\tfor p in (value or []):\n"
    "\t\tc = p.get('capacity_change_pct')\n"
    "\t\tout.append({'pump_id': p['pump_id'], 'status': p['status'], 'runs': p.get('runs', 0),\n"
    "\t\t\t'change': '' if c is None else '%+.0f%% vs this pump\\'s normal' % c,\n"
    "\t\t\t'evidence': p.get('quality', '')})\n"
    "\treturn out"
)

WARNINGS = (
    "\tout = []\n"
    "\tfor f in (value or []):\n"
    "\t\tchecks = f.get('inspection') or []\n"
    "\t\tout.append({'status': f['status'], 'alert_id': f['alert_id'],\n"
    "\t\t\t'title': (f.get('pump_id') or 'Station') + ': ' + f['type'].replace('_', ' ').lower(),\n"
    "\t\t\t'summary': f.get('summary', ''),\n"
    "\t\t\t'opened': 'Opened %s, flagged %s days' % (f.get('opened_on'), f.get('days_open')),\n"
    "\t\t\t'check': ('First check: ' + checks[0]) if checks else '', 'as_of': str(self.view.custom.as_of)})\n"
    "\treturn out"
)

SAFETY = (
    "\tif not value:\n"
    "\t\treturn 'No safety findings. SCADA-equivalent checks; real setpoints unknown.'\n"
    "\treturn '\\n'.join(['%s  %s  (since %s)' % (f['status'].replace('_', ' '), f.get('summary', ''), f.get('since_utc', '')) for f in value])"
)


WORK_ORDER = (
    "\timport urllib\n"
    "\tp = self.view.params\n"
    "\turl = '%s/api/evidence?alert_id=' + urllib.quote(str(p.alert_id)) + '&as_of_utc=' + urllib.quote(str(p.as_of))\n"
    "\ttry:\n"
    "\t\tw = system.util.jsonDecode(system.net.httpGet(url, 5000, 15000))['work_order']\n"
    "\t\tlines = ['WORK ORDER (DRAFT)', w['title'], '', 'Station: %%s   Pump: %%s   Priority: %%s' %% (w['station_id'], w.get('pump_id') or '-', w['priority']),\n"
    "\t\t\t'Requested by: ' + w['requested_by'], '', 'Checks:']\n"
    "\t\tlines += ['  [ ] ' + c for c in w['checks']]\n"
    "\t\tlines += ['', 'Evidence: ' + w['evidence_alert_id'], '', 'Caveats:'] + ['  - ' + c for c in w['caveats']]\n"
    "\t\ttext = '\\n'.join(lines)\n"
    "\texcept Exception as e:\n"
    "\t\ttext = 'Could not load the work order from the Dragonfly API: ' + str(e)\n"
    "\tsystem.perspective.openPopup('workorder', 'Cards/WorkOrder', params={'text': text}, title='Draft work order',\n"
    "\t\tmodal=True, showCloseIcon=True, draggable=True, resizable=True, position={'width': 620, 'height': 560})"
) % API

work_order_view = view_doc(flex("root", [
    label("Head", "Draft work order. Review and edit, then copy it into your maintenance system.",
          {"fontSize": "13px", "color": MUTED}),
    {"type": "ia.input.text-area", "meta": {"name": "Text"}, "position": {"grow": 1, "basis": "380px"},
     "props": {"text": "", "style": {"fontFamily": "monospace", "fontSize": "13px"}},
     "propConfig": {"props.text": prop("view.params.text")}},
    label("Foot", "Dragonfly never sends this anywhere and writes nothing to SCADA. A person decides what happens next.",
          {"fontSize": "12px", "color": MUTED}),
], style={"padding": "16px", "gap": "10px", "backgroundColor": PANEL}),
    params={"text": ""}, size=(520, 600))

# --- Embedded card views -------------------------------------------------------------------------------------------
warning_card = view_doc(flex("root", [
    flex("Top", [
        label("Chip", "", {"color": "#FFFFFF", "fontSize": "12px", "fontWeight": "700", "padding": "2px 10px",
                           "letterSpacing": "0.04em"},
              {"props.text": expr(WORDS.format(v="{view.params.status}")),
               "props.style.backgroundColor": expr(STATUS_BG.format(v="{view.params.status}"))}),
        label("Title", "", {"fontWeight": "600", "fontSize": "15px"}, {"props.text": prop("view.params.title")}),
    ], direction="row", alignItems="center", style={"gap": "10px"}),
    label("Summary", "", {"fontSize": "14px"}, {"props.text": prop("view.params.summary")}),
    label("Opened", "", {"fontSize": "13px", "color": MUTED}, {"props.text": prop("view.params.opened")}),
    label("Check", "", {"fontSize": "13px", "fontWeight": "600"}, {"props.text": prop("view.params.check")}),
    flex("Bottom", [
        label("Id", "", {"fontSize": "11px", "color": MUTED, "fontFamily": "monospace"}, {"props.text": prop("view.params.alert_id")}, grow=1),
        {"type": "ia.input.button", "meta": {"name": "WorkOrder"}, "position": {"basis": "170px", "shrink": 0},
         "props": {"text": "Draft work order", "style": {"backgroundColor": "#FFFFFF", "color": ADD, "border": "1px solid " + ADD,
                                                          "fontSize": "13px", "fontWeight": "600"}},
         "events": {"component": {"onActionPerformed": {"type": "script", "scope": "G", "config": {"script": WORK_ORDER}}}}},
    ], direction="row", alignItems="center", style={"gap": "10px", "marginTop": "4px"}),
], style={"backgroundColor": "#FFFFFF", "border": "1px solid " + LINE, "padding": "12px 14px", "gap": "4px"}),
    params={"status": "", "title": "", "summary": "", "opened": "", "check": "", "alert_id": "", "as_of": ""}, size=(165, 420))

# --- Main view -----------------------------------------------------------------------------------------------------
A = "{view.custom.a"

def counter(name, title, count_expr, border, color):
    return flex(name, [label("T", title, {"fontSize": "11px", "letterSpacing": "0.06em", "color": color}),
                       label("N", "", {"fontSize": "22px", "fontWeight": "600", "color": "#FFFFFF"},
                             {"props.text": expr(count_expr)})],
                style={"border": border, "padding": "5px 14px", "minWidth": "150px"})

# (scenario_id, label, stand-in station, moment to land on); dates checked against the live API
SCENARIOS = [("", "Real replay (Wessex)", "44371", "2022-06-05T00:00:00Z"),
             ("bloomington_morningside_2024_04_11:A", "Morningside A: pump wears out (sim.)", "44371", "2024-04-10T00:00:00Z"),
             ("bloomington_morningside_2024_04_11:B", "Morningside B: sudden trip (sim.)", "44371", "2024-04-11T08:00:00Z"),
             ("fishers_bowline_2009_01_20:A", "Fishers A: power lost (sim.)", "45385", "2009-01-20T10:45:00Z"),
             ("fishers_bowline_2009_01_20:B", "Fishers B: controller fault (sim.)", "45385", "2009-01-20T12:00:00Z")]
JUMP = ("\tjump = %s\n"
        "\tif currentValue is not None and currentValue.value in jump:\n"
        "\t\tself.custom.station, self.custom.as_of = jump[currentValue.value]") % repr(dict((k, (st, t)) for k, _, st, t in SCENARIOS))
scenario_dd = {"type": "ia.input.dropdown", "meta": {"name": "Scenario"}, "position": {"basis": "280px", "shrink": 0},
               "props": {"options": [{"value": k, "label": l} for k, l, _, _ in SCENARIOS], "value": "", "showClearIcon": False},
               "propConfig": {"props.value": prop("view.custom.scenario", bidirectional=True)}}
station_dd = {"type": "ia.input.dropdown", "meta": {"name": "Station"}, "position": {"basis": "200px", "shrink": 0},
              "props": {"options": [{"value": s, "label": "Wessex " + s} for s in ("44371", "45385", "45078")],
                        "value": "44371", "showClearIcon": False},
              "propConfig": {"props.value": prop("view.custom.station", bidirectional=True)}}
asof_tf = {"type": "ia.input.text-field", "meta": {"name": "AsOf"}, "position": {"basis": "210px", "shrink": 0},
           "props": {"text": ""}, "propConfig": {"props.text": prop("view.custom.as_of", bidirectional=True)}}

header = flex("Header", [
    flex("Where", [
        label("Crumb", "Collection System / Lift Stations", {"fontSize": "12px", "color": "#D5DADF"}),
        label("Name", "", {"fontSize": "20px", "fontWeight": "600", "color": "#FFFFFF"},
              {"props.text": expr("if(isNull(%s.error}), %s.display_name} + ' Lift Station', %s.error})" % (A, A, A))}),
        label("Data", "", {"fontSize": "12px", "color": "#D5DADF"},
              {"props.text": expr("if({view.custom.scenario} = '', 'REPLAY  ·  Wessex Water telemetry 2022-2023 (CC BY)  ·  not live data', "
                                  "'SIMULATION  ·  ' + {view.custom.scenario} + ' on stand-in station  ·  not real station data') "
                                  "+ '  ·  Data up to ' + {view.custom.as_of} + ' UTC'"),
               "props.style.color": expr("if({view.custom.scenario} = '', '#D5DADF', '#FFD08A')")}),
    ]),
    flex("Pick", [label("L0", "Scenario", {"color": "#D5DADF", "fontSize": "12px"}), scenario_dd,
                  label("L1", "Station", {"color": "#D5DADF", "fontSize": "12px"}), station_dd,
                  label("L2", "Data up to (UTC)", {"color": "#D5DADF", "fontSize": "12px"}), asof_tf],
         direction="row", alignItems="center", style={"gap": "8px"}),
    flex("Counts", [
        counter("Alarms", "SAFETY CHECKS (SCADA-EQUIV.)", "len(%s.safety})" % A, "1px solid #AEB5BC", "#D5DADF"),
        counter("Warnings", "EARLY WARNINGS (ADDED)", "len(%s.queue})" % A, "2px dashed " + ADD_LIGHT, "#BFD9FA"),
    ], direction="row", style={"gap": "12px"}),
], direction="row", wrap="wrap", justify="space-between", alignItems="center",
    style={"backgroundColor": "#2B3238", "padding": "10px 32px", "gap": "12px 32px"})

concept = label("Concept", "Mock-up of a utility SCADA screen with Dragonfly added. The utility's own graphics stay as they are. "
                "Dragonfly additions are outlined in dashed blue and labeled. Display only.",
                {"fontSize": "13px", "color": "#3B434B", "padding": "12px 32px 0"})

SVG = r"""
import base64
d = value or {}
pumps = d.get('pumps') or []
queue = d.get('queue') or []
days = dict([(f.get('pump_id'), f.get('days_open')) for f in queue if f.get('pump_id')])
def esc(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
C = {'INVESTIGATE': '#B42318', 'WATCH': '#B54708', 'SOURCE_OFFLINE': '#3B434B', 'INSUFFICIENT_EVIDENCE': '#6B7280'}
o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 420" font-family="Inter, Segoe UI, Arial, sans-serif">']
o.append('<rect x="20" y="100" width="170" height="18" fill="#8B95A0"/><polygon points="150,96 166,109 150,122" fill="#3B434B"/>')
o.append('<text x="20" y="90" font-size="12" fill="#4A5560">From collection system</text>')
o.append('<rect x="190" y="70" width="210" height="290" fill="#FFFFFF" stroke="#3B434B" stroke-width="2.5"/>')
o.append('<text x="295" y="62" font-size="12" font-weight="700" letter-spacing="1" fill="#3B434B" text-anchor="middle">WET WELL</text>')
o.append('<text x="295" y="210" font-size="13" fill="#4A5560" text-anchor="middle">Level shown by</text>')
o.append('<text x="295" y="228" font-size="13" fill="#4A5560" text-anchor="middle">utility SCADA</text>')
o.append('<line x1="400" y1="100" x2="414" y2="100" stroke="#3B434B" stroke-width="2"/><text x="418" y="104" font-size="11" fill="#4A5560">HIGH</text>')
o.append('<line x1="400" y1="330" x2="414" y2="330" stroke="#3B434B" stroke-width="2"/><text x="418" y="334" font-size="11" fill="#4A5560">LOW</text>')
n = max(len(pumps), 1)
ys = [150 + i * (150.0 / max(n - 1, 1)) for i in range(n)] if n > 1 else [240]
for y in ys:
    o.append('<rect x="400" y="%d" width="86" height="10" fill="#8B95A0"/><rect x="554" y="%d" width="40" height="10" fill="#8B95A0"/>' % (y - 5, y - 5))
o.append('<rect x="590" y="%d" width="10" height="%d" fill="#8B95A0"/>' % (ys[0] - 5, ys[-1] - ys[0] + 10))
o.append('<rect x="590" y="385" width="190" height="10" fill="#8B95A0"/><rect x="590" y="%d" width="10" height="%d" fill="#8B95A0"/>' % (ys[-1], 395 - ys[-1]))
o.append('<polygon points="764,378 780,390 764,402" fill="#3B434B"/><text x="610" y="378" font-size="12" fill="#4A5560">To force main</text>')
tag_y = 20
for p, y in zip(pumps, ys):
    st = p.get('status', '')
    o.append('<circle cx="520" cy="%d" r="34" fill="#E3E6E9" stroke="#3B434B" stroke-width="3"/>' % y)
    o.append('<text x="520" y="%d" font-size="16" font-weight="700" fill="#1B1F23" text-anchor="middle">%s</text>' % (y + 6, esc(p.get('pump_id'))))
    o.append('<text x="443" y="%d" font-size="10" fill="#3B434B" text-anchor="middle">%s runs today</text>' % (y - 10, p.get('runs', 0)))
    if st in C:
        c = p.get('capacity_change_pct')
        line1 = 'Capacity %+.0f%% vs normal' % c if c is not None else 'Capacity change unknown'
        line2 = ('Flagged %s days' % days[p['pump_id']]) if days.get(p['pump_id']) else ('Evidence: ' + p.get('quality', ''))
        o.append('<text x="610" y="%d" font-size="11" font-weight="700" letter-spacing="0.6" fill="#2D4A6B">ADDED BY EARLY WARNING</text>' % (tag_y + 12))
        o.append('<rect x="610" y="%d" width="180" height="112" fill="#FFFFFF" stroke="#2D4A6B" stroke-width="2" stroke-dasharray="6 4"/>' % (tag_y + 20))
        o.append('<text x="622" y="%d" font-size="11" font-weight="700" letter-spacing="0.6" fill="#3B434B">%s HEALTH</text>' % (tag_y + 40, esc(p.get('pump_id'))))
        lbl, hint = {'INVESTIGATE': ('Investigate', 'Inspect this pump'), 'WATCH': ('Watch', 'Capacity is dropping'),
                     'SOURCE_OFFLINE': ('Source offline', 'No data from the station'),
                     'INSUFFICIENT_EVIDENCE': ('Not enough data', 'Evidence too thin to judge')}[st]
        o.append('<rect x="622" y="%d" width="%d" height="22" fill="%s"/>' % (tag_y + 48, 34 + 8 * len(lbl), C[st]))
        o.append('<polygon points="634,%d 641,%d 627,%d" fill="#FFFFFF"/>' % (tag_y + 53, tag_y + 65, tag_y + 65))
        o.append('<text x="647" y="%d" font-size="12" font-weight="700" fill="#FFFFFF">%s</text>' % (tag_y + 64, esc(lbl)))
        o.append('<text x="622" y="%d" font-size="12" font-weight="700" fill="#1B1F23">%s</text>' % (tag_y + 88, esc(hint)))
        o.append('<text x="622" y="%d" font-size="12" fill="#1B1F23">%s</text>' % (tag_y + 104, esc(line1)))
        o.append('<text x="622" y="%d" font-size="12" fill="#1B1F23">%s</text>' % (tag_y + 120, esc(line2)))
        o.append('<line x1="548" y1="%d" x2="610" y2="%d" stroke="#2D4A6B" stroke-width="2" stroke-dasharray="4 3"/>' % (y - 20, tag_y + 68))
        tag_y += 134
if not pumps:
    o.append('<text x="520" y="240" font-size="13" fill="#4A5560" text-anchor="middle">No pump data</text>')
o.append('<text x="20" y="412" font-size="12" fill="#4A5560">Layout is illustrative. Pump tags use live Dragonfly results.</text></svg>')
return 'data:image/svg+xml;base64,' + base64.b64encode(''.join(o))
"""
SVG = "\n".join("\t" + l for l in SVG.strip("\n").split("\n"))

drawing = {"type": "ia.display.image", "meta": {"name": "Drawing"}, "position": {"basis": "460px", "shrink": 0},
           "props": {"fit": {"mode": "contain"}, "style": {"backgroundColor": "#FFFFFF", "border": "1px solid " + LINE}},
           "propConfig": {"props.source": prop("view.custom.a", SVG)}}

process = panel("Process", "Process view (mock-up of the utility's SCADA screen)",
                "Mock-up of a process screen. Pump health tags are added by Dragonfly; everything else stands in for the utility's graphics.", [
    drawing,
    flex("Legend", [
        label("L1", "\u25ad  Existing SCADA, unchanged", {"fontSize": "13px", "color": "#3B434B"}),
        label("L2", "\u2505  Added by Early Warning, display only", {"fontSize": "13px", "color": ADD}),
    ], direction="row", style={"gap": "24px"}),
    label("Rain", "", {"fontSize": "13px", "color": "#3B434B"},
          {"props.text": expr("if(isNull(%s.rain.last_72h_mm}), 'Rain data incomplete.', 'Rain: ' + "
                              "numberFormat(%s.rain.last_72h_mm}, '0.0') + ' mm in the last 72 h. "
                              "This measure is not affected by rain.')" % (A, A))}),
], basis="720px", grow=2)

alarms = panel("Alarms", "Alarm list", "SCADA-equivalent safety checks (high level, source silent). Never suppressed.", [
    label("List", "", {"fontSize": "14px", "whiteSpace": "pre-line"}, {"props.text": prop("view.custom.a.safety", SAFETY)}),
])

warnings = panel("Warnings", "Early warnings", "Added by the layer. Shown beside alarms, never mixed into them.", [
    label("Empty", "", {"fontSize": "14px", "color": MUTED},
          {"props.text": expr("if(%s.quality} = 'SUFFICIENT', 'No pumps need attention as of ' + {view.custom.as_of} + '.', "
                              "'Nothing flagged, but evidence is ' + if(%s.quality} = 'PARTIAL', 'Partial', 'Not enough data') + '.')"
                              % (A, A)),
           "position.display": expr("len(%s.queue}) = 0" % A)}),
    repeater("Cards", "Cards/WarningCard", WARNINGS, "view.custom.a.queue"),
    label("Expl", "", {"fontSize": "13px", "color": "#3B434B"}, {"props.text": expr("coalesce(%s.explanation}, '')" % A)}),
], dashed=True)

steps = [("1. UTILITY'S SCADA", "Level, pump on and off, rain", "Already logged in the historian. Nothing changes.", False),
         ("2. READ-ONLY EXPORT OR API", "Reads data, writes nothing", "No new sensors. No access to control systems.", False),
         ("3. DRAGONFLY LAYER", "Rain-cancelling pumping capacity", "Compares each pump with its own normal and its sibling.", True),
         ("4. DISPLAY ONLY", "Advisory tags and alerts", "On this SCADA screen and the planner dashboard.", True)]

connects = panel("Connects", "How the layer connects",
                 "Data flows one way, into the layer. Only advisory information comes back out.", [
    flex("Steps", [flex("Step%d" % i, [
        label("K", k, {"fontSize": "12px", "fontWeight": "700", "letterSpacing": "0.06em", "color": ADD if add else MUTED}),
        label("H", h, {"fontWeight": "600", "marginTop": "4px"}),
        label("D", d, {"fontSize": "13px", "color": MUTED, "marginTop": "2px"}),
    ], style={"backgroundColor": PANEL, "padding": "13px 15px",
              "border": ("2px dashed " + ADD) if add else ("1px solid " + LINE)}, basis="220px", grow=1)
        for i, (k, h, d, add) in enumerate(steps)], direction="row", wrap="wrap", style={"gap": "12px"}),
    label("Never", "What the layer never does: write to control tags, start or stop a pump, or change a setpoint.",
          {"fontSize": "14px", "fontWeight": "600"}),
])

footer = label("Prov", "", {"fontSize": "12px", "color": MUTED, "padding": "0 32px 24px", "fontFamily": "monospace"},
               {"props.text": expr("'model ' + coalesce(%s.provenance.model_version}, '?') + '  ·  source ' + "
                                   "left(coalesce(%s.provenance.source_hash}, ''), 12) + '  ·  origin ' + coalesce(%s.origin}, '')"
                                   % (A, A, A))})

main = view_doc(flex("root", [
    header, concept,
    flex("Content", [
        flex("Row", [process, flex("Side", [alarms, warnings], style={"gap": "16px"}, basis="400px", grow=1)],
             direction="row", wrap="wrap", alignItems="flex-start", style={"gap": "20px"}),
        connects,
    ], style={"padding": "20px 32px 16px", "gap": "24px"}),
    footer,
], style={"backgroundColor": "#D9DCDF", "fontFamily": "Inter, system-ui, sans-serif", "overflowY": "auto"}),
    custom={"station": "44371", "as_of": "2022-06-05T00:00:00Z", "scenario": "", "a": {}},
    prop_config={"custom.a": expr("{view.custom.station} + '|' + {view.custom.as_of} + '|' + {view.custom.scenario} + '|' + toStr(now(60000))", FETCH),
                 "custom.scenario": {"onChange": {"enabled": None, "script": JUMP}}})

persp = root / "com.inductiveautomation.perspective"
for name, doc in (("Dragonfly", main), ("Cards/WarningCard", warning_card), ("Cards/WorkOrder", work_order_view)):
    d = persp / "views" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "view.json").write_text(json.dumps(doc, indent=2))
    (d / "resource.json").write_text(json.dumps(resource(["view.json"]), indent=2))
(persp / "page-config").mkdir(parents=True, exist_ok=True)
(persp / "page-config" / "config.json").write_text(json.dumps({"pages": {"/": {"viewPath": "Dragonfly"}}}, indent=2))
(persp / "page-config" / "resource.json").write_text(json.dumps(resource(["config.json"]), indent=2))
(root / "project.json").write_text(json.dumps({"title": "Dragonfly", "description": "Read-only Dragonfly AI lift-station view",
                                               "enabled": True, "inheritable": False, "parent": ""}, indent=2))
print("wrote", root)
