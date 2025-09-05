# app.py
# Hi-PolicyLens | Streamlit 버전
# - RSS 목록 → 원문 텍스트 추출 → Potens.AI 정규화(JSON) → 테이블 + 요약 탭
# - "검색(빠름)"은 RSS만, "모두 요약"은 문서별 순차 요약(안전모드)
# - 세션 내에서 직전 실행과의 간단 diff도 제공

import os
import json
import time
import requests
import feedparser
import streamlit as st
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# -----------------------------
# 페이지 설정 & 기본 스타일
# -----------------------------
st.set_page_config(page_title="Hi-PolicyLens | 규제 비교 분석", layout="wide")
BRAND_ORANGE = "#dc8d32"
BRAND_NAVY   = "#0f2e69"

st.markdown(f"""
<style>
:root {{
  --brand-orange:{BRAND_ORANGE};
  --brand-navy:{BRAND_NAVY};
  --border:#e5e7eb;
  --surface:#f8f9fa;
}}
h1, h2, h3, h4 {{ color: {BRAND_NAVY}; }}
.small-muted {{ color:#6b7280; font-size:13px }}
.chip {{
  display:inline-block; padding:4px 10px; background:#f3f4f6; border:1px solid var(--border);
  border-radius:20px; font-size:12px; color:#6b7280; font-weight:500;
}}
.btn-link {{
  background:{BRAND_ORANGE}; color:white; text-decoration:none; padding:6px 10px; border-radius:6px; font-weight:600;
}}
.card {{
  background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px; margin-top:16px;
}}
hr {{ border-color:#eee }}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# 설정 (API 키)
# -----------------------------
POTENS_API_KEY = st.secrets.get("POTENS_API_KEY", os.getenv("POTENS_API_KEY", "PUT_YOUR_POTENS_API_KEY_HERE"))
POTENS_ENDPOINT = st.secrets.get("POTENS_ENDPOINT", os.getenv("POTENS_ENDPOINT", "https://ai.potens.ai/api/chat"))

# -----------------------------
# 유틸
# -----------------------------
SECTORS = ["solar","wind","hydro","nuclear"]
SECTOR_LABELS = {"solar":"태양광", "wind":"풍력", "hydro":"수력", "nuclear":"원자력"}

def region_from_url(url: str) -> str:
  try:
    host = urlparse(url).hostname or ""
    if host.endswith("cbp.gov"): return "북미"
    if host.endswith("motie.go.kr"): return "아시아"
    if host.endswith("europa.eu"): return "유럽"
  except:
    pass
  return ""

def html_to_text(html: str) -> str:
  soup = BeautifulSoup(html or "", "html.parser")
  for t in soup(["script", "style", "noscript"]): t.extract()
  text = soup.get_text(separator=" ")
  return " ".join(text.split())

def fetch_html(url: str, timeout=20) -> str:
  try:
    r = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent":"Hi-PolicyLens/Streamlit"})
    if r.status_code >= 200 and r.status_code < 300:
      r.encoding = r.apparent_encoding or r.encoding
      return r.text
  except:
    return ""
  return ""

def extract_json_array(s: str):
  if not s: return None
  t = s.strip().replace("```json","").replace("```","").strip()
  i, j = t.find("["), t.rfind("]")
  if i!=-1 and j!=-1 and j>i:
    try:
      arr = json.loads(t[i:j+1])
      return arr if isinstance(arr, list) else None
    except: pass
  try:
    arr = json.loads(t)
    return arr if isinstance(arr, list) else None
  except: return None

def build_prompt(text: str, origin: str) -> str:
  clipped = (text or "")[:6000]
  return f"""역할: 국제 규제 분석가
목표: 아래 원문에서 "신재생에너지 관련 규제"만 추출하여 JSON 배열로 정규화.

스키마:
[
  {{
    "jurisdiction": "국가/기관/지역",
    "law_or_policy": "법/정책/지침 명",
    "effective_date": "YYYY-MM-DD 또는 미상",
    "requirements": ["핵심 요건1","핵심 요건2"],
    "reporting": "보고/신고 주기 또는 방식(미상이면 'N/A')",
    "incentives": ["세제/보조 등"],
    "penalties": ["미이행시 제재"],
    "source": "원문 URL"
  }}
]

[원문 출처] {origin}
[원문]
{clipped}

반드시 **순수한 유효 JSON 배열([])**만 출력하세요.
- 마크다운/설명/코드펜스/주석/텍스트 금지
- JSON 외 문자를 포함하지 말 것
- 불확실하면 빈 배열([]) 반환"""

def normalize_with_ai(text: str, origin_url: str):
  if not POTENS_API_KEY or POTENS_API_KEY.startswith("PUT_"):
    # 키 미설정 시 폴백: 빈 배열
    return []
  prompt = build_prompt(text, origin_url)
  try:
    r = requests.post(
      POTENS_ENDPOINT,
      headers={"Authorization": f"Bearer {POTENS_API_KEY}", "Content-Type":"application/json", "Accept":"application/json"},
      json={"prompt": prompt},
      timeout=40,
    )
    body = r.text or ""
    if r.headers.get("content-type","").startswith("application/json"):
      try:
        j = r.json()
        body = j.get("response") or j.get("text") or j.get("content") or body
      except: pass
  except Exception as e:
    return []
  arr = extract_json_array(body) or []
  # 정규화
  out = []
  for it in arr:
    out.append({
      "jurisdiction": it.get("jurisdiction",""),
      "law_or_policy": it.get("law_or_policy",""),
      "effective_date": it.get("effective_date","N/A"),
      "requirements": it.get("requirements",[]) if isinstance(it.get("requirements",[]), list) else [],
      "reporting": it.get("reporting","N/A"),
      "incentives": it.get("incentives",[]) if isinstance(it.get("incentives",[]), list) else [],
      "penalties": it.get("penalties",[]) if isinstance(it.get("penalties",[]), list) else [],
      "source": it.get("source", origin_url)
    })
  return out

def key_of(item: dict) -> str:
  return f"{item.get('jurisdiction','')}|{item.get('law_or_policy','')}"

# -----------------------------
# RSS (빠름)
# -----------------------------
DEFAULT_FEEDS = [
  "https://www.cbp.gov/rss/trade.xml",
  "https://www.motie.go.kr/rss/rssView.do?bbs_cd_n=81",
  "https://echa.europa.eu/documents/10162/21645696/rss.xml",
]

def fetch_feed_list(feed_urls, query: str):
  entries = []
  for url in feed_urls:
    try:
      feed = feedparser.parse(url)
      for e in feed.entries:
        if not getattr(e, "title", None) or not getattr(e, "link", None):
          continue
        entries.append({
          "title": e.title,
          "link": e.link,
          "pubDate": getattr(e, "published", "") or getattr(e,"updated",""),
          "source": url,
          "region": region_from_url(e.link),
        })
    except:
      pass
  # 필터 & 정렬 & 상한
  q = (query or "").lower().strip()
  if q:
    entries = [x for x in entries if q in x["title"].lower()]
  entries.sort(key=lambda x: str(x["pubDate"]), reverse=True)
  return entries[:40]

# -----------------------------
# 세션 상태
# -----------------------------
if "list_rows" not in st.session_state: st.session_state["list_rows"] = []
if "normalized_rows" not in st.session_state: st.session_state["normalized_rows"] = []  # 이번 실행 결과(정규화 아이템들)
if "prev_normalized_rows" not in st.session_state: st.session_state["prev_normalized_rows"] = []  # 직전 실행 결과(세션 내)

# -----------------------------
# 헤더
# -----------------------------
st.title("Hi-PolicyLens")
st.caption("국내외 규제 차이를 체계적으로 비교하여 투자 리스크를 분석합니다.")

# -----------------------------
# 툴바
# -----------------------------
col1, col2, col3, col4 = st.columns([1,2,1,1])
with col1:
  sector = st.selectbox("섹터", SECTORS, index=0, format_func=lambda s: SECTOR_LABELS.get(s,s))
with col2:
  query = st.text_input("필터 키워드(예: renewable, RPS, FIT 등)", value="")
with col3:
  run_btn = st.button("검색(빠름)", use_container_width=True)
with col4:
  reset_btn = st.button("초기화", use_container_width=True)

st.divider()

# -----------------------------
# 동작: 검색(빠름)
# -----------------------------
if run_btn:
  st.session_state["prev_normalized_rows"] = st.session_state.get("normalized_rows", []).copy()
  st.session_state["normalized_rows"] = []  # 이번 실행 결과 초기화
  with st.spinner("RSS 목록 가져오는 중…"):
    feed_urls = DEFAULT_FEEDS  # 필요 시 섹터별로 다르게 구성 가능
    rows = fetch_feed_list(feed_urls, query)
    st.session_state["list_rows"] = rows

if reset_btn:
  st.session_state["list_rows"] = []
  st.session_state["normalized_rows"] = []
  st.session_state["prev_normalized_rows"] = []

# -----------------------------
# 탭
# -----------------------------
tab1, tab2 = st.tabs(["개요", "요약/비교"])

with tab1:
  st.subheader("국가별 규제 문서 목록")
  st.caption(f"{SECTOR_LABELS.get(sector,sector)} 분야의 최신 문서 목록입니다. 문서별 **요약**을 눌러 정규화하세요.")
  rows = st.session_state.get("list_rows", [])
  if not rows:
    st.info("검색(빠름)을 먼저 실행하세요.")
  else:
    # 목록 렌더
    cols = ["국가/관할","지역","제목","요약","원문"]
    st.write("")
    container = st.container()
    all_btn_col = st.columns([1,4,1,1,1])[2]
    with all_btn_col:
      all_sum = st.button("모두 요약(안전모드)", type="primary")
    if all_sum:
      prog = st.progress(0, text="모두 요약 중…")
      norm_all = []
      for i, r in enumerate(rows):
        html = fetch_html(r["link"])
        text = html_to_text(html)[:6000]
        items = normalize_with_ai(text, r["link"])
        # 정규화 없는 경우 폴백으로 제목 기반 최소 항목
        if not items:
          items = [{
            "jurisdiction": "",
            "law_or_policy": r["title"],
            "effective_date": "N/A",
            "requirements": [],
            "reporting": "N/A",
            "incentives": [],
            "penalties": [],
            "source": r["link"]
          }]
        # 세션에 누적
        for it in items:
          norm_all.append({
            **it,
            "region": r["region"],
            "link": r["link"],
            "title": r["title"]
          })
        prog.progress((i+1)/len(rows))
        time.sleep(0.2)  # 과도한 호출 방지용 살짝 딜레이
      st.session_state["normalized_rows"] = norm_all
      st.success(f"요약/정규화 완료: {len(norm_all)}개 아이템")
    # 표 형태로 리스트 + 개별 요약 버튼
    for i, r in enumerate(rows):
      with st.container():
        c1, c2, c3, c4, c5 = st.columns([1,1,4,3,1])
        c1.markdown("**N/A**")  # 요약 전이라 국가/관할은 비움
        c2.markdown(f"<span class='chip'>{r['region'] or ''}</span>", unsafe_allow_html=True)
        c3.write(r["title"])
        sum_key = f"sum_{i}"
        if c4.button("요약", key=sum_key):
          with st.spinner("요약/정규화 중…"):
            html = fetch_html(r["link"])
            text = html_to_text(html)[:6000]
            items = normalize_with_ai(text, r["link"])
            if not items:
              items = [{
                "jurisdiction": "",
                "law_or_policy": r["title"],
                "effective_date": "N/A",
                "requirements": [],
                "reporting": "N/A",
                "incentives": [],
                "penalties": [],
                "source": r["link"]
              }]
            # 세션에 누적
            for it in items:
              st.session_state["normalized_rows"].append({
                **it,
                "region": r["region"],
                "link": r["link"],
                "title": r["title"]
              })
            st.success(f"요약 완료 ({len(items)}개)")
        c5.markdown(f"<a class='btn-link' href='{r['link']}' target='_blank'>원문</a>", unsafe_allow_html=True)
      st.markdown("<hr/>", unsafe_allow_html=True)

with tab2:
  st.subheader("요약 결과 / 비교")
  norm = st.session_state.get("normalized_rows", [])
  prev = st.session_state.get("prev_normalized_rows", [])

  # 1) 요약 결과 테이블
  if not norm:
    st.info("아직 요약/정규화된 데이터가 없습니다. 개요 탭에서 [요약] 또는 [모두 요약]을 실행하세요.")
  else:
    st.markdown("#### 요약/정규화 결과")
    table_rows = []
    for n in norm:
      table_rows.append({
        "국가/관할": n.get("jurisdiction") or "N/A",
        "지역": n.get("region") or "",
        "보고서 제목": n.get("law_or_policy") or (n.get("title") or "N/A"),
        "주요 규제 요건": "; ".join(n.get("requirements") or []),
        "발효일": n.get("effective_date") or "N/A",
        "보고": n.get("reporting") or "N/A",
        "원문": n.get("source") or n.get("link") or ""
      })
    st.dataframe(table_rows, use_container_width=True, height=min(560, 40+28*len(table_rows)))

  # 2) 직전 실행과 간단 diff(세션 한정)
  if prev and norm:
    st.markdown("#### 변화 리포트 (이번 실행 vs 직전 실행)")
    # 맵 구성
    def to_map(arr):
      m = {}
      for it in arr:
        k = key_of(it)
        m[k] = it
      return m
    A = to_map(prev)
    B = to_map(norm)
    added, removed, updated = [], [], []
    for k, v in B.items():
      if k not in A:
        added.append(v)
      else:
        changes = []
        fields = ["effective_date","reporting","requirements","incentives","penalties","law_or_policy"]
        for f in fields:
          av = json.dumps(A[k].get(f,""), ensure_ascii=False)
          bv = json.dumps(v.get(f,""), ensure_ascii=False)
          if av != bv:
            changes.append({"field": f, "before": A[k].get(f,""), "after": v.get(f,"")})
        if changes: updated.append({"after": v, "before": A[k], "changes": changes})
    for k, v in A.items():
      if k not in B: removed.append(v)

    st.caption(f"신규 {len(added)} · 변경 {len(updated)} · 삭제 {len(removed)}")
    colA, colB, colC = st.columns(3)
    with colA:
      st.write("**신규**")
      if not added: st.write("없음")
      for it in added:
        st.markdown(f"- **{it.get('jurisdiction') or 'N/A'} · {it.get('law_or_policy') or 'N/A'}**")
    with colB:
      st.write("**변경**")
      if not updated: st.write("없음")
      for ch in updated:
        st.markdown(f"- **{ch['after'].get('jurisdiction') or 'N/A'} · {ch['after'].get('law_or_policy') or 'N/A'}**")
        for c in ch["changes"]:
          st.markdown(f"  - {c['field']}: :red[`{str(c['before'])[:80]}`] → :green[`{str(c['after'])[:80]}`]")
    with colC:
      st.write("**삭제**")
      if not removed: st.write("없음")
      for it in removed:
        st.markdown(f"- **{it.get('jurisdiction') or 'N/A'} · {it.get('law_or_policy') or 'N/A'}**")

# 하단 안내
st.markdown("<div class='small-muted'>Tip: Streamlit Cloud에서는 `Settings → Secrets`에 POTENS_API_KEY를 넣어두면 안전합니다. (지금은 코드 안의 플레이스홀더를 사용 중)</div>", unsafe_allow_html=True)
