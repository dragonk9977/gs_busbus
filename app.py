import html as H
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import streamlit.components.v1 as components

import bus

KST = ZoneInfo("Asia/Seoul")
st.set_page_config(page_title="퇴근길 버스 알리미", page_icon="🚌", layout="wide")

# ── 경로 정의 (정류장 번호/노선명은 여기서만 수정) ─────────────────
ROUTES = [
    dict(label="① 18810 · 27번", short="① 27번·독산", ars="18810", route="27", off="18643", color="#2f6fed", side="right",
         t_ars="18553", t_route="금천07", dest="18558", walk=3, ride=15, walk_t=4, ride2=10),
    dict(label="② 18517 · 금천05", short="② 금천05·독산", ars="18517", route="금천05", off="18643", color="#1fa971", side="left",
         t_ars="18553", t_route="금천07", dest="18558", walk=3, ride=15, walk_t=4, ride2=10),
    dict(label="③ 18500 · 금천05", short="③ 금천05·가산", ars="18500", route="금천05", off="18594", color="#8b5cf6", side="right",
         t_ars="18503", t_route="금천03", dest="18530", walk=3, ride=15, walk_t=4, ride2=10),
]
WINDOW = (17, 19)  # 이 시간대(시)에만 자동 조회 → API 일일 한도(1,000건) 보호
ORANGE = "#ff6b00"

st.markdown("""
<style>
.block-container{padding-top:3.2rem;max-width:1200px}
header[data-testid="stHeader"]{display:none}
[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none}
h1{font-size:1.7rem!important;padding:.2rem 0 .6rem!important}
.chipx{font-size:.74rem;font-weight:600;border-radius:6px;padding:1px 7px;background:rgba(128,128,128,.18);white-space:nowrap}
@media (max-width:640px){
.hero{padding:16px 16px;margin-bottom:14px}.hero .big{font-size:2.3rem}.hero .ht{font-size:1.02rem}.hero .hs{font-size:.88rem}
.card{padding:14px 14px 8px}.card .big{font-size:1.9rem}.stp{font-size:.86rem;padding:6px 0}.stp .sub{font-size:.76rem}
}
.hero{background:linear-gradient(135deg,#ff8a2b,#ff5200);color:#fff;border-radius:20px;padding:20px 24px;margin:4px 0 18px;box-shadow:0 6px 18px rgba(255,82,0,.25)}
.hero .hl{font-size:.8rem;font-weight:700;letter-spacing:.08em;opacity:.9}
.hero .ht{font-size:1.15rem;font-weight:700;margin-top:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hero .big{font-size:2.9rem;font-weight:800;line-height:1.15;margin:6px 0 4px}
.hero .big .sm{font-size:1.1rem;font-weight:600;opacity:.9}
.hero .hs{font-size:.95rem;opacity:.95}
.no{width:28px;height:28px;border-radius:50%;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:.95rem;flex:none}
.card{border:1px solid rgba(128,128,128,.28);border-radius:18px;padding:16px 18px 10px;background:rgba(128,128,128,.06);height:100%}
.card.best{border:2px solid #ff6b00;background:rgba(255,107,0,.07)}
.card.off{opacity:.85}
.card .hd{display:flex;align-items:center;gap:8px;font-weight:700;font-size:1.05rem}
.card .tag{margin-left:auto;background:#ff6b00;color:#fff;border-radius:8px;padding:1px 9px;font-size:.75rem;font-weight:700}
.card .stn{opacity:.65;font-size:.85rem;margin:2px 0 6px 36px}
.card .big{font-size:2.2rem;font-weight:800;line-height:1.15;margin:4px 0 8px}
.card .big .sm{font-size:.95rem;font-weight:600;opacity:.7}
.stp{display:flex;align-items:flex-start;gap:10px;padding:7px 0;border-top:1px dashed rgba(128,128,128,.28);font-size:.92rem}
.stp .ic{width:22px;text-align:center;flex:none}
.stp .tx{flex:1}
.stp .rt{font-weight:700;white-space:nowrap}
.stp .sub{opacity:.6;font-size:.8rem}
.sec{font-size:.78rem;font-weight:700;opacity:.55;margin:10px 0 2px}
.badge{display:inline-block;border-radius:6px;padding:0 7px;color:#fff;font-weight:700;font-size:.85rem}
</style>
""", unsafe_allow_html=True)

st.title("🚌 퇴근길 버스 알리미")

# ── 설정 (체크하면 위쪽에 펼쳐짐. 닫아도 값은 유지) ────────────────────
ss = st.session_state
vals = ss.setdefault("vals", {})


def S(key, default):
    """설정값: 화면에 슬라이더가 있으면 그 값, 없으면 마지막에 저장된 값"""
    v = ss.get("s_" + key, vals.get(key, default))
    vals[key] = v
    return v


def setting(key, label, lo, hi, default, step=1):
    ss.setdefault("s_" + key, vals.get(key, default))
    v = st.slider(label, lo, hi, step=step, key="s_" + key)
    vals[key] = v
    return v


show_set = st.checkbox("⚙️ 설정 (갱신 주기 · 알림 · 소요시간)", key="show_set")
if show_set:
    refresh = setting("refresh", "자동 갱신 주기(초)", 20, 90, 40, 5)
    alert_min = setting("alert", "승차 알림 기준(분 전)", 1, 10, 3)
    ss.setdefault("s_any", vals.get("any", False))
    anytime = st.checkbox(f"{WINDOW[0]}~{WINDOW[1]}시 외에도 자동 조회", key="s_any")
    vals["any"] = anytime
    edit_label = st.radio("소요시간을 고칠 경로", [r["short"] for r in ROUTES], horizontal=True, key="s_edit")
    edit_idx = [r["short"] for r in ROUTES].index(edit_label)
else:
    refresh, alert_min, anytime = S("refresh", 40), S("alert", 3), S("any", False)
    edit_idx = None

cfg = []
for i, r in enumerate(ROUTES):
    if i == edit_idx:
        walk = setting(f"{i}_walk", "1층 → 승차 정류장 도보(분)", 0, 15, r["walk"])
        ride = setting(f"{i}_ride", f"{r['route']} 승차 → {r['off']} 하차(분) · 실시간 없을 때 값", 1, 60, r["ride"])
        walk_t = setting(f"{i}_walk_t", f"{r['off']} → {r['t_ars']} 도보(분)", 0, 15, r["walk_t"])
        ride2 = setting(f"{i}_ride2", f"{r['t_route']} 승차 → {r['dest']} 하차(분) · 실시간 없을 때 값", 1, 60, r["ride2"])
    else:
        walk, ride = S(f"{i}_walk", r["walk"]), S(f"{i}_ride", r["ride"])
        walk_t, ride2 = S(f"{i}_walk_t", r["walk_t"]), S(f"{i}_ride2", r["ride2"])
    cfg.append({**r, "walk": walk, "ride": ride, "walk_t": walk_t, "ride2": ride2})

try:
    KEY = st.secrets["BUS_API_KEY"]
except Exception:
    st.error("Secrets에 BUS_API_KEY 가 없습니다. (.streamlit/secrets.toml 또는 Streamlit Cloud → Secrets)")
    st.stop()
try:
    KAKAO_JS_KEY = st.secrets["KAKAO_JS_KEY"]
except Exception:
    KAKAO_JS_KEY = ""
try:
    KAKAO_REST_KEY = st.secrets["KAKAO_REST_KEY"]      # 선택: 있으면 도로를 따라 경로를 그림
except Exception:
    KAKAO_REST_KEY = ""


@st.cache_resource
def api_counter():
    return {"day": "", "n": 0}


def count_call():
    c, today = api_counter(), datetime.now(KST).strftime("%Y-%m-%d")
    if c["day"] != today:
        c["day"], c["n"] = today, 0
    c["n"] += 1


@st.cache_data(ttl=15, show_spinner=False)
def load(ars):
    """승차 정류장: 매 갱신마다 새로 조회. 반환 (도착목록, 정류장정보, 조회시각)"""
    count_call()
    arr, stop = bus.fetch_station(ars, KEY)
    return arr, stop, time.time()


@st.cache_data(ttl=90, show_spinner=False)
def load_slow(ars):
    """환승 정류장: 호출 한도 절약을 위해 90초에 한 번"""
    count_call()
    arr, stop = bus.fetch_station(ars, KEY)
    return arr, stop, time.time()


@st.cache_data(ttl=120, show_spinner=False)
def load_route(route_id):
    """노선 전체 도착정보(차량ID 포함) → 실제 주행시간 계산용. 2분에 한 번"""
    count_call()
    return bus.fetch_route_all(route_id, KEY), time.time()


def mmss(sec):
    sec = int(sec)
    return f"{sec // 60}분 {sec % 60:02d}초"


def short(sec):
    return "곧 도착" if sec < 30 else f"{round(sec / 60)}분 후"


# ── 카카오맵 ─────────────────────────────────────────
MAP_HTML = """
<div id="wrap" style="position:relative;width:100%;height:360px;border-radius:14px;overflow:hidden">
  <div id="m" style="position:absolute;left:0;top:0;right:0;bottom:0"></div>
  <svg id="ln" style="position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:5"></svg>
  <div id="lb" style="position:absolute;left:0;top:0;right:0;bottom:0;pointer-events:none;z-index:6"></div>
</div>
<script>
function err(t){
  const at = (document.referrer || location.href || '').split('/').slice(0,3).join('/');
  document.getElementById('m').innerHTML='<div style="padding:22px;font:14px/1.6 sans-serif;color:#c0392b">'+t+
    '<br><br><span style="color:#555">지금 접속 주소: <b>'+at+'</b><br>카카오 콘솔의 JS SDK 도메인에 이 주소가 <b>그대로</b> 등록돼 있어야 합니다.</span></div>';
}
</script>
<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey=%%KEY%%&autoload=false"
        onerror="err('카카오맵 SDK 로드 실패: 키, 도메인 등록, 카카오맵 사용 설정, 네트워크(차단) 중 하나가 원인입니다.')"></script>
<script>
const DATA = %%PTS%%;
const pts = DATA.pts, paths = DATA.paths;
if (typeof kakao === 'undefined' || !kakao.maps) {
  err('카카오맵 SDK가 응답하지 않습니다: 키, 도메인 등록, 카카오맵 사용 설정을 확인하세요.');
} else kakao.maps.load(function () {
  const wrap = document.getElementById('wrap'), lb = document.getElementById('lb'), ln = document.getElementById('ln');
  const map = new kakao.maps.Map(document.getElementById('m'),
      {center: new kakao.maps.LatLng(pts[0].lat, pts[0].lng), level: 3, draggable: false});
  map.setZoomable(false);   // 화면 고정: 드래그·확대/축소 비활성
  const bounds = new kakao.maps.LatLngBounds();
  pts.forEach(p => {
    p.pos = new kakao.maps.LatLng(p.lat, p.lng);
    bounds.extend(p.pos);
    p.bc = p.best ? '%%ORANGE%%' : p.color;
    new kakao.maps.CustomOverlay({map: map, position: p.pos, zIndex: 3, content:
      '<div style="width:34px;height:34px;border-radius:50%;background:' + p.bc + ';color:#fff;border:3px solid #fff;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;' +
      'font:700 16px sans-serif">' + p.no + '</div>'});
    const el = document.createElement('div');
    el.style.cssText = 'position:absolute;left:0;top:0;background:#fff;color:#222;border-radius:10px;padding:5px 9px;' +
      'border-left:6px solid ' + p.bc + ';box-shadow:0 2px 8px rgba(0,0,0,.35);font:12px/1.4 sans-serif;white-space:nowrap';
    el.innerHTML = p.html;
    lb.appendChild(el);
    p.el = el;
  });
  paths.forEach(pa => {
    const line = pa.coords.map(c => new kakao.maps.LatLng(c[0], c[1]));
    line.forEach(l => bounds.extend(l));
    new kakao.maps.Polyline({map: map, path: line, strokeWeight: pa.dash ? 4 : 6, strokeColor: pa.color,
                             strokeOpacity: pa.dash ? 0.85 : 0.9, strokeStyle: pa.dash ? 'shortdash' : 'solid'});
  });
  if (pts.length > 1 || paths.length) map.setBounds(bounds, 120, 150, 60, 150);

  // 이름표 배치: 마커·다른 이름표와 안 겹치는 자리를 골라 놓고, 가는 선으로 마커와 연결
  function layout() {
    const W = wrap.clientWidth, H = wrap.clientHeight, pj = map.getProjection();
    const it = pts.map(p => {
      const q = pj.containerPointFromCoords(p.pos);
      return {p: p, x: q.x, y: q.y, w: p.el.offsetWidth, h: p.el.offsetHeight};
    });
    const mk = it.map(i => ({l: i.x - 20, t: i.y - 20, r: i.x + 20, b: i.y + 20}));
    const area = (a, c) => Math.max(0, Math.min(a.r, c.r) - Math.max(a.l, c.l)) *
                           Math.max(0, Math.min(a.b, c.b) - Math.max(a.t, c.t));
    const outside = a => (a.r - a.l) * (a.b - a.t) - area(a, {l: 4, t: 4, r: W - 4, b: H - 4});
    const dirs = [[0, -1], [1, 0], [-1, 0], [0, 1], [1, -1], [-1, -1], [1, 1], [-1, 1]];
    const SIDE = {top: [0, -1], right: [1, 0], left: [-1, 0], bottom: [0, 1]};
    const order = it.slice().sort((a, c) => (c.p.best ? 1 : 0) - (a.p.best ? 1 : 0));
    const placed = [];
    let lines = '';
    order.forEach(i => {
      let best = null;
      const pref = SIDE[i.p.side] || null;   // 정류장이 있는 쪽(방향)을 우선 사용
      [32, 64, 104].forEach(d => dirs.forEach((dir, k) => {
        const cx = i.x + dir[0] * (dir[0] ? i.w / 2 + d : 0);
        const cy = i.y + dir[1] * (dir[1] ? i.h / 2 + d : 0);
        const r = {l: cx - i.w / 2, t: cy - i.h / 2, r: cx + i.w / 2, b: cy + i.h / 2};
        let s = outside(r) * 50 + d * 0.3 + k * 1.5 +
                ((pref && dir[0] === pref[0] && dir[1] === pref[1]) ? 0 : 40);
        mk.forEach(m => { s += area(r, m) * 30; });
        placed.forEach(q => { s += area(r, q) * 30; });
        if (!best || s < best.s) best = {s: s, r: r};
      }));
      placed.push(best.r);
      i.p.el.style.left = best.r.l + 'px';
      i.p.el.style.top = best.r.t + 'px';
      const px = Math.min(Math.max(i.x, best.r.l), best.r.r);
      const py = Math.min(Math.max(i.y, best.r.t), best.r.b);
      const dist = Math.hypot(px - i.x, py - i.y);
      if (dist > 22) {
        const ux = (px - i.x) / dist, uy = (py - i.y) / dist;
        lines += '<line x1="' + (i.x + ux * 19) + '" y1="' + (i.y + uy * 19) + '" x2="' + px + '" y2="' + py +
                 '" stroke="' + i.p.bc + '" stroke-width="2.5" stroke-linecap="round"/>';
      }
    });
    ln.innerHTML = lines;
  }
  kakao.maps.event.addListener(map, 'bounds_changed', layout);
  kakao.maps.event.addListener(map, 'idle', layout);
  layout();
  setTimeout(layout, 300);
});
</script>
"""


def show_boarding_map(points, paths=None):
    if not KAKAO_JS_KEY:
        st.warning("카카오맵을 쓰려면 Secrets에 `KAKAO_JS_KEY`(카카오 JavaScript 키)를 추가하세요. "
                   "(Web 도메인에 `http://localhost:8501` 등록 필요)")
        return
    if not points:
        st.caption("정류장 좌표를 아직 못 받았습니다. (도착 버스가 하나도 없으면 좌표도 오지 않아요)")
        return
    page = (MAP_HTML.replace("%%KEY%%", KAKAO_JS_KEY).replace("%%ORANGE%%", ORANGE)
            .replace("%%PTS%%", json.dumps({"pts": points, "paths": paths or []}, ensure_ascii=False)))
    if hasattr(st, "iframe"):          # 최신 Streamlit
        st.iframe(page, height=375)
    else:                              # 구버전 호환
        components.html(page, height=375)


# ── 카드 ─────────────────────────────────────────
def step(icon, text, right="", sub=""):
    s = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="stp"><span class="ic">{icon}</span><span class="tx">{text}{s}</span>'
            f'<span class="rt">{right}</span></div>')


STATUS = {"ok": ("🟢", "탈 수 있어요"), "tight": ("🟠", "뛰면 가능"), "miss": ("⚪", "타기 어려워요")}


def arrivals_block(arrs, walk_min):
    rows = []
    for a in arrs[:2]:
        ic, txt = STATUS[bus.status(a.eta_sec, walk_min * 60)]
        rows.append(step(ic, f"<b>{mmss(a.eta_sec)}</b> 후",
                         f'<span class="chipx">{txt}{" · 만차" if a.full else ""}</span>'))
    return "".join(rows) or step("⚠️", "도착 정보 없음")


def card_html(o, r, stop_name, arrs_here, hm, is_best):
    no = r["label"].split()[0]
    head = (f'<div class="hd"><span class="no" style="background:{r["color"]}">{no}</span>'
            f'<span>{H.escape(r["route"])}번 승차</span>'
            f'{"<span class=tag>추천</span>" if is_best else ""}</div>'
            f'<div class="stn">{H.escape(stop_name)} · {r["ars"]}</div>')
    arr_rows = f'<div class="sec">이 정류장 도착 예정</div>{arrivals_block(arrs_here, r["walk"])}'
    if not o.boarded:
        note = step("ℹ️", "지금은 탈 수 있는 버스가 없어 환승 계산을 건너뛰었어요") if arrs_here else ""
        return f'<div class="card off">{head}{arr_rows}{note}</div>'
    big = f'<div class="big">{mmss(o.boarded.eta_sec)}<span class="sm"> 후 도착</span></div>'
    steps = [
        step("🚶", f"1층 → 승차장 도보 {r['walk']}분"),
        step("🚌", f'<span class="badge" style="background:{r["color"]}">{H.escape(r["route"])}</span> 승차',
             f"{mmss(o.boarded.eta_sec)}"),
        step("🚏", f"{r['off']} 하차", hm(o.ride_end_sec), f"주행 {o.ride_used:.0f}분 · {o.ride_src}"),
        step("🚶", f"{r['t_ars']} 정류장까지 도보 {r['walk_t']}분"),
    ]
    if o.transfer:
        est = " (추정)" if o.transfer.estimated else ""
        steps.append(step("🔁", f'<span class="badge" style="background:#555">{H.escape(r["t_route"])}</span> 환승',
                          f"대기 {mmss(o.transfer_wait_sec)}{est}"))
        steps.append(step("🏁", f"{r['dest']} 하차", hm(o.home_stop_sec), f"주행 {o.ride2_used:.0f}분 · {o.ride2_src}"))
    else:
        for n in o.notes:
            steps.append(step("⚠️", n))
    return (f'<div class="card{" best" if is_best else ""}">{head}{big}{arr_rows}'
            f'<div class="sec">이동 경로</div>{"".join(steps)}</div>')


# ── 데이터 스냅샷 (API는 refresh초마다만 호출, 화면 숫자는 1초마다 계산) ─────────────
STOPS = sorted({x for r in cfg for x in (r["ars"], r["t_ars"])})


def is_active():
    now = datetime.now(KST)
    return anytime or (WINDOW[0] <= now.hour < WINDOW[1] and now.weekday() < 5)


def fetch_snapshot():
    st.session_state["last_try"] = time.time()
    first = {r["ars"] for r in cfg}
    try:
        loaded = {x: (load(x) if x in first else load_slow(x)) for x in STOPS}
    except Exception as e:
        st.session_state["snap_err"] = str(e)
        return
    st.session_state["snap_err"] = ""
    coords = st.session_state.setdefault("coords", {})
    rids = st.session_state.setdefault("rids", {})
    for k, v in loaded.items():
        if v[1]:
            coords[k] = v[1]          # 한 번 받은 좌표는 계속 보관
    for r in cfg:                      # 노선ID 기억 (도착 버스가 없을 때도 쓰도록)
        for ars, name in ((r["ars"], r["route"]), (r["t_ars"], r["t_route"])):
            m = bus.pick(loaded[ars][0], name)
            if m and m[0].route_id:
                rids[(ars, name)] = m[0].route_id
    routes = {}
    for rid in set(rids.values()):
        try:
            routes[rid] = load_route(rid)
        except Exception:
            pass                       # 실패하면 설정값으로 대체
    st.session_state["snap"] = {"t": time.time(), "loaded": loaded, "routes": routes}


def get_snapshot():
    first_visit = "last_try" not in st.session_state       # 페이지를 처음 연 순간: 시간대와 상관없이 한 번 조회
    stale = time.time() - st.session_state.get("last_try", 0) >= refresh
    if first_visit or (is_active() and stale):              # 이후 자동 갱신은 퇴근 시간대에만
        fetch_snapshot()
    return st.session_state.get("snap")


def compute():
    """마지막으로 받은 도착정보에서 '경과 시간'을 빼서 지금 기준 남은 시간으로 다시 계산"""
    snap = get_snapshot()
    if not snap:
        return None
    now = time.time()
    data = {k: [replace(a, eta_sec=int(a.eta_sec - (now - v[2]))) for a in v[0] if a.eta_sec - (now - v[2]) >= 0]
            for k, v in snap["loaded"].items()}
    rids, routes = st.session_state.get("rids", {}), snap["routes"]

    def ride_fn(rid, board, off, fallback):
        def f(arr):
            ro = routes.get(rid)
            if not ro:
                return fallback, "설정값"
            items, ts = ro
            target = None if (arr is None or arr.estimated) else arr.eta_sec + (now - ts)
            got = bus.choose_ride(bus.segment_rides(items, board, off), target)
            if got is None:
                return fallback, "설정값"
            return got[0] / 60, "실시간" if got[1] == "bus" else "실시간(구간)"
        return f

    opts = [bus.plan_option(
                r["label"], r["route"], data[r["ars"]], r["walk"],
                ride_fn(rids.get((r["ars"], r["route"])), r["ars"], r["off"], r["ride"]),
                r["walk_t"], bus.pick(data[r["t_ars"]], r["t_route"]),
                ride_fn(rids.get((r["t_ars"], r["t_route"])), r["t_ars"], r["dest"], r["ride2"]))
            for r in cfg]
    coords = st.session_state.get("coords", {})
    return dict(now=datetime.now(KST), t=snap["t"], el=now - snap["t"], data=data, opts=opts,
                best=bus.recommend(opts), coords=coords,
                name_of=lambda ars: coords.get(ars, {}).get("name", f"정류장 {ars}"))


MODES = ["자동 추천"] + [r["short"] for r in ROUTES]


def selected_idx():
    """사용자가 고른 경로 번호(0,1,2). 자동 추천이면 None"""
    m = st.session_state.get("mode", MODES[0])
    return None if m == MODES[0] or m not in MODES else MODES.index(m) - 1


def arr_label(a, walk_min):
    t, stt = short(a.eta_sec), bus.status(a.eta_sec, walk_min * 60)
    if stt == "tight":
        return f'<span style="color:#e67e22">{t} 🏃</span>'
    return t if stt == "ok" else f'<span style="color:#aaa">{t} ✕</span>'


# ── 좌표·경로선 ─────────────────────────────────────
@st.cache_resource
def coord_store():
    return {}


def get_coord(ars):
    """정류장 좌표. 이미 받은 것 → 저장소 → (없으면) 한 번 조회. 버스가 없어 좌표가 안 오면 5분 뒤 재시도"""
    c = st.session_state.get("coords", {}).get(ars)
    if c:
        return c
    store = coord_store()
    e = store.get(ars)
    if e and e["stop"]:
        return e["stop"]
    if e and time.time() - e["t"] < 300:
        return None
    count_call()
    try:
        stop = bus.fetch_station(ars, KEY)[1]
    except Exception:
        stop = None
    store[ars] = {"stop": stop, "t": time.time()}
    return stop


@st.cache_data(show_spinner=False)
def _road(lat1, lng1, lat2, lng2, rest_key):
    r = requests.get("https://apis-navi.kakaomobility.com/v1/directions",
                     params={"origin": f"{lng1},{lat1}", "destination": f"{lng2},{lat2}", "priority": "RECOMMEND"},
                     headers={"Authorization": f"KakaoAK {rest_key}"}, timeout=8)
    r.raise_for_status()
    rt = r.json()["routes"][0]
    if rt.get("result_code", 0) != 0:
        raise RuntimeError(rt.get("result_msg", "경로 없음"))
    pts = []
    for sec in rt["sections"]:
        for rd in sec["roads"]:
            v = rd["vertexes"]
            pts += [[v[i + 1], v[i]] for i in range(0, len(v) - 1, 2)]
    step = max(1, len(pts) // 250)
    return pts[::step] + [pts[-1]]


def path_between(a, b):
    if KAKAO_REST_KEY:
        try:
            return _road(a["lat"], a["lng"], b["lat"], b["lng"], KAKAO_REST_KEY)
        except Exception:
            pass                       # 실패하면 직선으로 대체
    return [[a["lat"], a["lng"]], [b["lat"], b["lng"]]]


def focus_map(v, sel):
    """내가 고른 경로만: 승차→하차→환승→도착 정류장과 이동 경로"""
    o, r = v["opts"][sel], cfg[sel]
    now = v["now"]
    hm = lambda sec: (now + timedelta(seconds=sec)).strftime("%H:%M")
    pts, paths, cs = [], [], {}

    def add(key, ars, no, html, side, best=False):
        c = get_coord(ars)
        cs[key] = c
        if c:
            pts.append({"lat": c["lat"], "lng": c["lng"], "best": best, "color": r["color"],
                        "no": no, "side": side, "html": html})

    here = bus.pick(v["data"][r["ars"]], r["route"])[:2]
    times = " · ".join(arr_label(a, r["walk"]) for a in here) if here else "도착 정보 없음"
    badge = ('<span style="background:#ff6b00;color:#fff;border-radius:5px;padding:0 6px;'
             'margin-right:5px;font-size:11px">내 경로</span>')
    add("b", r["ars"], r["label"].split()[0],
        f'{badge}<b>{H.escape(r["route"])}번</b> {times}'
        f'<div style="font-size:11px;color:#777">승차 · {H.escape(v["name_of"](r["ars"]))}</div>', r["side"], True)
    off_t = f' · {hm(o.ride_end_sec)}' if o.boarded else ""
    sub = f'<div style="font-size:11px;color:#777">주행 {o.ride_used:.0f}분 · {o.ride_src}</div>' if o.boarded else ""
    add("o", r["off"], "🚏", f'<b>하차</b> {r["off"]}{off_t}{sub}', "top")
    tr = f' · 대기 {mmss(o.transfer_wait_sec)}' if o.transfer else ""
    add("t", r["t_ars"], "🔁", f'<b>{H.escape(r["t_route"])} 환승</b>{tr}'
        f'<div style="font-size:11px;color:#777">{r["t_ars"]} · 도보 {r["walk_t"]}분</div>', "bottom")
    dn = f' · {hm(o.home_stop_sec)}' if o.home_stop_sec else ""
    add("d", r["dest"], "🏁", f'<b>도착</b> {r["dest"]}{dn}', "right")

    if cs.get("b") and cs.get("o"):
        paths.append({"coords": path_between(cs["b"], cs["o"]), "color": r["color"], "dash": False})
    if cs.get("o") and cs.get("t"):
        paths.append({"coords": [[cs["o"]["lat"], cs["o"]["lng"]], [cs["t"]["lat"], cs["t"]["lng"]]],
                      "color": "#555", "dash": True})
    if cs.get("t") and cs.get("d"):
        paths.append({"coords": path_between(cs["t"], cs["d"]), "color": r["color"], "dash": False})
    return pts, paths


@st.fragment(run_every=1)
def hero_frag():
    err = st.session_state.get("snap_err")
    if err:
        st.error(f"도착정보 조회 실패: {err}")
    v = compute()
    if not v:
        return
    now, best, opts = v["now"], v["best"], v["opts"]
    hm = lambda sec: (now + timedelta(seconds=sec)).strftime("%H:%M")
    n_calls = api_counter()["n"]
    st.caption(f"{datetime.fromtimestamp(v['t'], KST):%H:%M:%S} 조회 ({int(v['el'])}초 전) · "
               f"{refresh}초마다 갱신 · API {n_calls}/1,000")
    if n_calls >= 900:
        st.warning("오늘 API 호출이 한도(1,000회)에 가까워요. 갱신 주기를 늘리거나 화면을 닫아 주세요.")

    sel = selected_idx()
    target = opts[sel] if sel is not None else best
    if sel is not None and not target.boarded:
        r = cfg[sel]
        nxt = bus.pick(v["data"][r["ars"]], r["route"])
        st.warning(f"{r['label']} · 지금은 탈 수 있는 {r['route']}번이 없어요"
                   + (f" (다음 도착 {mmss(nxt[0].eta_sec)} 후)" if nxt else " (도착 정보 없음)"))
        return
    if not target:
        st.warning("지금 조회되는 경로가 없습니다. (운행 종료/도착정보 없음)")
        return
    r = cfg[opts.index(target)]
    no = r["label"].split()[0]
    est = " (추정)" if (target.transfer and target.transfer.estimated) else ""
    tail_txt = (f'{H.escape(r["t_route"])} 환승 대기 {mmss(target.transfer_wait_sec)}{est} · '
                f'<b>{r["dest"]}</b> 도착 예상 <b>{hm(target.home_stop_sec)}</b>'
                if target.transfer else "환승 버스 정보 없음")
    st.markdown(
        f'<div class="hero"><div class="hl">{"내가 고른 경로" if sel is not None else "지금 추천 경로"}</div>'
        f'<div class="ht"><span class="no" style="background:#fff;color:#ff5200">{no}</span>'
        f'{H.escape(v["name_of"](r["ars"]))} 승차장 · {H.escape(r["route"])}번</div>'
        f'<div class="big">{mmss(target.boarded.eta_sec)}<span class="sm"> 후 도착</span></div>'
        f'<div class="hs">도보 {r["walk"]}분 · {tail_txt}</div></div>',
        unsafe_allow_html=True)
    if target.boarded.eta_sec <= alert_min * 60:        # 같은 버스에 대한 알림은 한 번만
        key = (r["ars"], int((time.time() + target.boarded.eta_sec) / 60))
        done = st.session_state.setdefault("toasted", set())
        if key not in done:
            done.add(key)
            st.toast(f"{r['route']}번 곧 도착! ({mmss(target.boarded.eta_sec)})", icon="🚌")


@st.fragment(run_every=refresh)
def map_frag():
    v = compute()
    if not v:
        return
    sel = selected_idx()
    if sel is not None:
        pts, paths = focus_map(v, sel)
        show_boarding_map(pts, paths)
        if paths and not KAKAO_REST_KEY:
            st.caption("경로선은 정류장 사이를 직선으로 이은 것입니다. Secrets에 `KAKAO_REST_KEY`를 넣으면 도로를 따라 그려요.")
        elif paths:
            st.caption("경로선은 도로 기준의 대략적인 경로이며 실제 버스 노선과 조금 다를 수 있어요.")
        return
    pts = []
    for o, r in zip(v["opts"], cfg):
        c = v["coords"].get(r["ars"])
        if not c:
            continue
        here = bus.pick(v["data"][r["ars"]], r["route"])[:2]
        times = " · ".join(arr_label(a, r["walk"]) for a in here) if here else "도착 정보 없음"
        is_best = o is v["best"]
        badge = ('<span style="background:#ff6b00;color:#fff;border-radius:5px;padding:0 6px;'
                 'margin-right:5px;font-size:11px">추천</span>') if is_best else ""
        pts.append({"lat": c["lat"], "lng": c["lng"], "best": is_best, "color": r["color"],
                    "no": r["label"].split()[0], "side": r["side"],
                    "html": f'{badge}<b>{H.escape(r["route"])}번</b> {times}'
                            f'<div style="font-size:11px;color:#777">{H.escape(c["name"])}'
                            f'{" · 도보 " + str(r["walk"]) + "분" if r["walk"] else ""}</div>'})
    show_boarding_map(pts)


def render_cards(v, idxs, best_idx):
    now = v["now"]
    hm = lambda sec: (now + timedelta(seconds=sec)).strftime("%H:%M")
    for col, i in zip(st.columns(len(idxs)), idxs):
        r, o = cfg[i], v["opts"][i]
        with col:
            st.markdown(card_html(o, r, v["name_of"](r["ars"]), bus.pick(v["data"][r["ars"]], r["route"]),
                                  hm, i == best_idx), unsafe_allow_html=True)


@st.fragment(run_every=1)
def cards_frag():
    v = compute()
    if not v:
        return
    sel = selected_idx()
    if sel is None:
        best_idx = v["opts"].index(v["best"]) if v["best"] else None
        render_cards(v, list(range(len(cfg))), best_idx)
    else:                               # 고른 경로만 크게
        left, _ = st.columns([3, 2])
        with left:
            render_cards(v, [sel], sel)


@st.fragment(run_every=refresh)
def others_frag():
    sel = selected_idx()
    v = compute() if sel is not None else None
    if not v:
        return
    if st.checkbox("다른 경로도 보기", key="show_others"):
        render_cards(v, [i for i in range(len(cfg)) if i != sel], None)


@st.fragment(run_every=refresh)
def raw_frag():
    v = compute()
    if not v:
        return
    if st.checkbox("원본 도착정보 보기", key="show_raw"):
        for name in STOPS:
            rows = [{"노선": x.route, "남은시간": mmss(x.eta_sec), "메시지": x.msg,
                     "혼잡도": {"3": "여유", "4": "보통", "5": "혼잡"}.get(x.congestion, "-")}
                    for x in sorted(v["data"][name], key=lambda x: x.eta_sec)]
            st.write(f"**{name}** · {v['name_of'](name)}")
            st.table(rows)


if not is_active():
    st.caption(f"열 때 한 번 조회했어요 · 자동 갱신은 평일 {WINDOW[0]}~{WINDOW[1]}시에만")
    if st.button("지금 다시 조회"):
        fetch_snapshot()

st.radio("내 경로 (고르면 그 경로만 보여줘요)", MODES, horizontal=True, key="mode")
hero_frag()
map_frag()
st.markdown("&nbsp;", unsafe_allow_html=True)
cards_frag()
others_frag()
raw_frag()
st.caption("※ Streamlit은 화면을 열어둬야 갱신·알림됩니다. 데이터: 서울특별시 버스도착정보(공공데이터포털)")
