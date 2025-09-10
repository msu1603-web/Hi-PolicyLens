import os, requests, textwrap, random

class RetrieverClient:
    """
    팀원 검색 API가 생기면 base_url을 넣고 아래 주석 부분을 실제 엔드포인트에 맞추면 됩니다.
    없으면 데모용 Mock 데이터를 반환합니다.
    """
    def __init__(self, base_url=None, api_key=None, timeout=30):
        self.base_url = (base_url or os.getenv("RETRIEVER_BASE_URL") or "").rstrip("/")
        self.api_key  = api_key or os.getenv("RETRIEVER_API_KEY")
        self.timeout  = timeout

    def search(self, query, k=8):
        if self.base_url:
            url = f"{self.base_url}/search"
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            r = requests.post(url, headers=headers, json={"query": query, "k": k}, timeout=self.timeout)
            r.raise_for_status()
            return r.json()

        # ---- 데모 Mock 결과 ----
        dummy = textwrap.dedent("""
        태양광 발전 보조금 단가는 2020년 이후 단계적으로 하향 조정되었다.
        2021년 고시에서 소형 설비에 대한 상한이 축소되었으며, 신청 자격 요건에 유지보수 계획 제출이 추가되었다.
        2022년에는 REC 가중치 산정 기준이 개정되며 농촌 지역 설비에 대한 우대 조항이 도입되었다.
        2023년에는 자가소비형 설비의 세액공제 범위가 확대되었다.
        2024년에는 동일 부지 중복 지원을 제한하는 규정이 신설되었다.
        """).strip()
        rows = []
        for i in range(min(k,5)):
            rows.append({
                "doc_id": f"신재생_정책보고서_{2020+i}",
                "page_start": random.randint(5,20),
                "page_end": random.randint(21,40),
                "line_start": random.randint(10,30),
                "line_end": random.randint(31,60),
                "text": dummy
            })
        return rows
