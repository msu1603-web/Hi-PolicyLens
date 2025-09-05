# app.py
# Hi-PolicyLens | Streamlit 버전 (공공기관 3곳 전용)
# - motie.go.kr (RSS), cbp.gov (RSS), echa.europa.eu/legislation (HTML 파싱)
# - 검색(빠름): 목록만 불러오기
# - 요약/모두 요약: 문서별 Potens.AI 정규화

import os, json, time, requests, feedparser, streamlit as st
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

st.set_page_config(page_title="Hi-PolicyLens | 규제 비교 분석", layout="wide")
BRAND_ORANGE = "#dc8d32"; BRAND_NAVY = "#0f2e69"
st.markdown(f"""
<style>
:root {{ --brand-orange:{BRAND_ORANGE}; --brand-navy:{BRAND_NAVY}; --border:#e5e7eb; --surface:#f8f9fa; }}
h1, h2, h3, h4 {{ color: {BRAND_NAVY}; }}
.small-muted {{ color:#6b7280; font-size:13px }}
.chip {{ display:inline-block; padding:4px 10px; background:#f3f4f6; border:1px solid var(--border);
  border-radius:20px; font-size:12px; color:#6b7280; font-weight:500; }}
.btn-link {{ background:{BRAND_ORANGE}; color:white; text-decoration:none; padding:6px 10px; border-radius:6px; font-weight:600; }}
.card {{ background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px; margin-top:16px; }}
hr {{ border-color:#eee }}
</style>
""", unsafe_allow_html=True)

# --- Secrets / ENV ---
POTENS_API_KEY = st.secrets.get("POTENS_API_KEY", os.getenv("POTENS_API_KEY", "PUT_YOUR_POTENS_API_KEY_HERE"))
POTENS_ENDPOINT = st.secrets.get("POTENS_ENDPOINT", os.getenv("POTENS_ENDPOINT", "https://ai.potens.ai/api/chat"))

SECTORS = ["solar","wind","hydro","nuclear"]
SECTOR_LABELS = {"solar":"태양광","wind":"풍력","hydro":"수력","nuclear":"원자력"}

def region_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        if host.endswith("cbp.gov"): return "북미"
        if host.endswith("motie.go.kr"): return "아시아"
        if host.endswith("europa.eu"): return "유럽"
    except: pass
    return ""

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script","style","noscript"]): t.extract()
    return " ".join(soup.get_text(" ").split())

def fetch_html(url: str, timeout=20) -> str:
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True,
                         headers={"User-Agent":"Hi-PolicyLens/Streamlit"})
        if 200 <= r.status_code < 300:
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
    except: return ""
    return ""

def extract_json_array(s: str):
    if not s: return None
    t = s.strip().replace("```json","").replace("```","").strip()
    i, j = t.find("["), t.rfind("]")
    if i!=-1 and j!=-1 and j>i:
        try:
            arr = json.loads(t[i:j+1])
            return arr if isinstance(arr,list) else None
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
    if not POTENS_API_KEY or POTENS_API_KEY.startswith("PUT_"):  # 키 미설정 시 폴백
        return []
    prompt = build_prompt(text, origin_url)
    try:
        r = requests.post(
            POTENS_ENDPOINT,
            headers={"Authorization": f"Bearer {POTENS_API_KEY}",
                     "Content-Type":"application/json","Accept":"application/json"},
            json={"prompt": prompt}, timeout=40
        )
        body = r.text or ""
        if r.headers.get("content-type","").startswith("application/json"):
            try:
                j = r.json()
                body = j.get("response") or j.get("text") or j.get("content") or body
            except: pass
    except: return []
    arr = extract_json_array(body) or []
    out = []
    for it in arr:
        out.append({
            "jurisdiction": it.get("jurisdiction",""),
            "law_or_policy": it.get("law_or_policy",""),
            "effective_date": it.get("effective_date","N/A"),
            "requirements": it.get("requirements",[]) if isinstance(it.get("requirements",[]),list) else [],
            "reporting": it.get("reporting","N/A"),
            "incentives": it.get("incentives",[]) if isinstance(it.get("incentives",[]),list) else [],
            "penalties": it.get("penalties",[]) if isinstance(it.get("penalties",[]),list) else [],
            "source": it.get("source", origin_url)
        })
    return out

def key_of(item: dict) -> str:
    return f"{item.get('jurisdiction','')}|{item.get('law_or_policy','')}"

# -----------------------------
# 공공기관 3곳 소스 정의
# -----------------------------
SOURCES = [
    # 1) MOTIE 보도자료 RSS
    {"type":"rss", "url":"https://www.motie.go.kr/rss/rssView.do?bbs_cd_n=81"},
    # 2) CBP 무역 공지 RSS
    {"type":"rss", "url":"https://www.cbp.gov/rss/trade.xml"},
    # 3) ECHA Legislation (HTML 목록 파싱)
    {"type":"html", "url":"https://echa.europa.eu/legislation"}
]

def fetch_from_rss(url: str):
    feed = feedparser.parse(url)
    out = []
    for e in getattr(feed, "entries", []) or []:
        if not getattr(e,"title",None) or not getattr(e,"link",None): continue
        out.append({
            "title": e.title,
            "link": e.link,
            "pubDate": getattr(e,"published","") or getattr(e,"updated",""),
            "source": url,
            "region": region_from_url(e.link)
        })
    return out

def fetch_from_echa_legislation(url: str):
    """ECHA 법령 페이지에서 목록형 링크/제목을 긁어온다."""
    html = fetch_html(url)
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    # 페이지 구조가 바뀔 수 있으므로 a태그 전수 검사 후 법령/지침 관련 섹션만 취사
    anchors = soup.select("a")
    for a in anchors:
        title = (a.get_text(strip=True) or "")
        href = a.get("href") or ""
        if not title or not href: continue
        # 절대경로화
        link = urljoin(url, href)
        # 거친 필터: 내부 문서/법령 상세로 이어지는 것 우선
        if "legislation" in link or "regulation" in link or "directive" in link or "law" in link:
            out.append({
                "title": title,
                "link": link,
                "pubDate": "",  # 페이지에 날짜가 일관적이지 않음
                "source": url,
                "region": region_from_url(link)
            })
    # 중복 제거(링크 기준)
    seen = set(); uniq=[]
    for x in out:
        if x["link"] in seen: continue
        seen.add(x["link"]); uniq.append(x)
    # 제목 길이 기준으로 너무 짧은 노이즈 제거
    uniq = [x for x in uniq if len(x["title"]) >= 8]
    return uniq[:40]

def fetch_feed_list(query: str):
    entries = []
    # 디버깅 표시용 박스
    dbg = st.empty()
    logs = []
    for src in SOURCES:
        kind, url = src["type"], src["url"]
        try:
            logs.append(f"🔎 Fetch: {kind.upper()} - {url}")
            if kind == "rss":
                items = fetch_from_rss(url)
            else:
                items = fetch_from_echa_legislation(url)
            logs.append(f"   → {len(items)} items")
            entries.extend(items)
        except Exception as ex:
            logs.append(f"   ❌ Error: {ex}")
        dbg.write("\n".join(logs))
    # 필터 + 정렬 + 상한
    q = (query or "").lower().strip()
    if q: entries = [x for x in entries if q in (x["title"] or "").lower()]
    entries.sort(key=lambda x: str(x["pubDate"]), reverse=True)
    return entries[:60]

# -----------------------------
# 세션 상태
# -----------------------------
if "list_rows" not in st.session_state: st.session_state["list_rows"] = []
if "normalized_rows" not in st.session_state: st.session_state["normalized_rows"] = []
if "prev_normalized_rows" not in st.session_state: st.session_state["prev_normalized_rows"] = []

# -----------------------------
# 헤더/툴바
# -----------------------------
st.title("Hi-PolicyLens")
st.caption("국내외 규제 차이를 체계적으로 비교하여 투자 리스크를 분석합니다.")
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

if run_btn:
    st.session_state["prev_normalized_rows"] = st.session_state.get("normalized_rows", []).copy()
    st.session_state["normalized_rows"] = []
    with st.spinner("공공기관 3곳에서 목록 수집 중…"):
        rows = fetch_feed_list(query)
        st.session_state["list_rows"] = rows
        if not rows:
            st.info("수집된 항목이 없습니다. 잠시 후 다시 시도하세요.")
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
    st.caption("문서별 **요약**을 눌러 정규화하세요. (ECHA는 목록 페이지 → 세부 문서로 이동해 요약됩니다)")
    rows = st.session_state.get("list_rows", [])
    if not rows:
        st.info("검색(빠름)을 먼저 실행하세요.")
    else:
        cols = st.columns([1,4,1])
        with cols[1]:
            all_sum = st.button("모두 요약(안전모드)", type="primary")
        if all_sum:
            prog = st.progress(0, text="모두 요약 중…")
            acc = []
            for i, r in enumerate(rows):
                html = fetch_html(r["link"])
                text = html_to_text(html)[:6000]
                items = normalize_with_ai(text, r["link"])
                if not items:
                    items = [{
                        "jurisdiction":"", "law_or_policy": r["title"], "effective_date":"N/A",
                        "requirements":[], "reporting":"N/A", "incentives":[], "penalties":[], "source": r["link"]
                    }]
                for it in items:
                    acc.append({ **it, "region": r["region"], "link": r["link"], "title": r["title"] })
                prog.progress((i+1)/len(rows))
                time.sleep(0.2)
            st.session_state["normalized_rows"] = acc
            st.success(f"요약/정규화 완료: {len(acc)}개")
        # 목록 렌더 + 개별 요약
        for i, r in enumerate(rows):
            with st.container():
                c1, c2, c3, c4 = st.columns([1,4,3,1])
                c1.markdown(f"<span class='chip'>{r['region'] or ''}</span>", unsafe_allow_html=True)
                c2.write(r["title"])
                if c3.button("요약", key=f"sum_{i}"):
                    with st.spinner("요약/정규화 중…"):
                        html = fetch_html(r["link"])
                        text = html_to_text(html)[:6000]
                        items = normalize_with_ai(text, r["link"])
                        if not items:
                            items = [{
                                "jurisdiction":"", "law_or_policy": r["title"], "effective_date":"N/A",
                                "requirements":[], "reporting":"N/A", "incentives":[], "penalties":[], "source": r["link"]
                            }]
                        for it in items:
                            st.session_state["normalized_rows"].append({ **it, "region": r["region"], "link": r["link"], "title": r["title"] })
                        st.success(f"요약 완료 ({len(items)}개)")
                c4.markdown(f"<a class='btn-link' href='{r['link']}' target='_blank'>원문</a>", unsafe_allow_html=True)
            st.markdown("<hr/>", unsafe_allow_html=True)

with tab2:
    st.subheader("요약 결과 / 비교")
    norm = st.session_state.get("normalized_rows", [])
    prev = st.session_state.get("prev_normalized_rows", [])

    if not norm:
        st.info("요약/정규화된 데이터가 없습니다. 개요 탭에서 [요약] 또는 [모두 요약]을 실행하세요.")
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

    # 직전 실행 대비 간단 diff (세션 한정)
    if prev and norm:
        st.markdown("#### 변화 리포트 (이번 실행 vs 직전 실행)")
        def to_map(arr):
            m={}; 
            for it in arr: m[f"{it.get('jurisdiction','')}|{it.get('law_or_policy','')}"]=it
            return m
        A, B = to_map(prev), to_map(norm)
        added, removed, updated = [], [], []
        for k, v in B.items():
            if k not in A: added.append(v)
            else:
                changes=[]
                for f in ["effective_date","reporting","requirements","incentives","penalties","law_or_policy"]:
                    av = json.dumps(A[k].get(f,""), ensure_ascii=False)
                    bv = json.dumps(v.get(f,""), ensure_ascii=False)
                    if av!=bv: changes.append({"field":f,"before":A[k].get(f,""),"after":v.get(f,"")})
                if changes: updated.append({"after":v,"before":A[k],"changes":changes})
        for k, v in A.items():
            if k not in B: removed.append(v)
        st.caption(f"신규 {len(added)} · 변경 {len(updated)} · 삭제 {len(removed)}")
        colA, colB, colC = st.columns(3)
        with colA:
            st.write("**신규**"); 
            if not added: st.write("없음")
            for it in added: st.markdown(f"- **{it.get('jurisdiction') or 'N/A'} · {it.get('law_or_policy') or 'N/A'}**")
        with colB:
            st.write("**변경**"); 
            if not updated: st.write("없음")
            for ch in updated:
                st.markdown(f"- **{ch['after'].get('jurisdiction') or 'N/A'} · {ch['after'].get('law_or_policy') or 'N/A'}**")
                for c in ch["changes"]:
                    st.markdown(f"  - {c['field']}: :red[`{str(c['before'])[:80]}`] → :green[`{str(c['after'])[:80]}`]")
        with colC:
            st.write("**삭제**"); 
            if not removed: st.write("없음")
            for it in removed: st.markdown(f"- **{it.get('jurisdiction') or 'N/A'} · {it.get('law_or_policy') or 'N/A'}**")

st.markdown("<div class='small-muted'>Tip: Streamlit Cloud에서는 Settings → Secrets에 POTENS_API_KEY, POTENS_ENDPOINT를 TOML로 저장하세요.</div>", unsafe_allow_html=True)
