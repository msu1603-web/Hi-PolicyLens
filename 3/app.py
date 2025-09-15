import streamlit as st
import requests
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import chromadb
import uuid # 고유 ID 생성을 위해 추가

# --- 1. 핵심 기능 함수 정의 ---

# PDF에서 텍스트를 추출하는 함수
def get_pdf_text(pdf_docs):
    text = ""
    for pdf in pdf_docs:
        pdf_reader = PdfReader(pdf)
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

# 텍스트를 의미 있는 단위(청크)로 나누는 함수
def get_text_chunks(text):
    # 여기서는 간단하게 문단 단위로 나눕니다.
    # 더 정교하게 나누려면 LangChain 같은 라이브러리를 사용할 수 있습니다.
    chunks = text.split('\n\n')
    return [chunk for chunk in chunks if chunk.strip()] # 내용이 있는 청크만 반환

# 청크를 벡터로 변환하고 데이터베이스에 저장하는 함수
def get_vectorstore(text_chunks):
    # 무료 공개된 한국어 임베딩 모델을 사용합니다.
    # 이 모델이 문장의 '의미'를 숫자의 배열(벡터)로 바꿔줍니다.
    model = SentenceTransformer('jhgan/ko-sroberta-multitask')

    # ChromaDB 클라이언트를 생성합니다. (메모리에서 실행되어 간단합니다)
    client = chromadb.Client()

    # 'pdf_collection' 이라는 이름의 컬렉션(데이터 저장 공간)을 만듭니다.
    # 만약 이미 있다면 기존 것을 사용합니다.
    collection = client.get_or_create_collection(name="pdf_collection")

    # 각 청크에 대해 고유 ID를 생성하고 임베딩(벡터 변환)하여 저장합니다.
    for i, chunk in enumerate(text_chunks):
        collection.add(
            embeddings=[model.encode(chunk).tolist()], # 문장을 벡터로 변환
            documents=[chunk], # 원문 텍스트 저장
            ids=[str(uuid.uuid4())] # 고유한 ID 부여
        )
    return collection, model

# 질문과 가장 유사한 청크를 벡터 데이터베이스에서 찾는 함수
def search_similar_chunks(collection, model, user_question):
    # 사용자 질문도 동일한 모델을 사용해 벡터로 변환합니다.
    question_embedding = model.encode(user_question).tolist()
    
    # DB에서 가장 유사한 청크 3개를 찾습니다. (n_results=3)
    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=3
    )
    return results['documents'][0] # 유사한 청크의 원문 텍스트들을 반환

# 생성형 AI에게 답변을 요청하는 함수
def get_ai_answer(context, question, api_key):
    # Potens.ai API 엔드포인트와 헤더 정보
    url = "https://ai.potens.ai/api/chat"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    # *** 가장 중요한 부분: 프롬프트 엔지니어링 ***
    # AI가 답변을 지어내지 않고, 반드시 주어진 내용에서 '발췌'하도록 강제하는 명령
    prompt = f"""
    당신은 오직 주어진 '문서 내용' 안에서만 정보를 찾아서 답변해야 하는 AI 어시스턴트입니다.

    [지시사항]
    1. 사용자의 '질문'에 대한 답변을 아래 '문서 내용'에서 찾으십시오.
    2. 답변은 반드시 '문서 내용'에 있는 문장이나 문단을 **그대로 복사하여 붙여넣어야 합니다.**
    3. 절대 내용을 요약하거나, 다른 단어로 바꾸거나, 새로운 문장을 만들지 마십시오.
    4. 만약 '문서 내용'에서 질문에 대한 답을 찾을 수 없다면, 다른 어떤 말도 하지 말고 오직 "관련 정보를 찾을 수 없음" 이라고만 답변하십시오.

    [문서 내용]
    {context}

    [질문]
    {question}

    [답변]
    """

    data = {"prompt": prompt}

    # API에 요청 보내기
    response = requests.post(url, headers=headers, json=data)
    
    # 응답 결과 처리
    if response.status_code == 200:
        return response.json().get("choices")[0].get("message").get("content")
    else:
        return f"API 호출에 실패했습니다: {response.status_code} - {response.text}"


# --- 2. Streamlit 웹 앱 화면 구성 ---

def main():
    st.set_page_config(page_title="맞춤형 문서 분석 AI 툴", page_icon="🤖")
    st.header("📄 문서 기반 Q&A 시스템")
    st.write("PDF 파일을 업로드하고, 문서 내용에 대해 질문해보세요.")
    
    # API 키를 사이드바에서 입력받습니다.
    # st.secrets를 사용해 배포 환경에서는 안전하게 키를 관리합니다.
    try:
        # Streamlit 클라우드에 배포된 경우 secrets에서 키를 가져옴
        api_key = st.secrets["POTENS_API_KEY"]
    except:
        # 로컬에서 실행하거나 secrets 설정이 없는 경우 사용자 입력을 받음
        api_key = st.sidebar.text_input("Potens.ai API 키를 입력하세요:", type="password")

    # PDF 파일 업로드
    uploaded_files = st.file_uploader("분석할 PDF 파일을 선택하세요.", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        if st.button("PDF 처리 및 분석 준비"):
            with st.spinner("PDF 문서를 읽고 분석 중입니다... 잠시만 기다려주세요."):
                # 1. PDF에서 텍스트 추출
                raw_text = get_pdf_text(uploaded_files)
                
                # 2. 텍스트를 청크로 분할
                text_chunks = get_text_chunks(raw_text)
                
                # 3. 벡터 데이터베이스 생성 및 저장 (세션 상태에 저장하여 재사용)
                st.session_state.vectorstore, st.session_state.model = get_vectorstore(text_chunks)
                
                st.success("분석 준비가 완료되었습니다! 이제 아래에서 질문을 입력하세요.")

    # 사용자 질문 입력
    if 'vectorstore' in st.session_state: # 분석 준비가 완료되었을 때만 질문창 표시
        user_question = st.text_input("문서 내용에 대해 질문하세요:")

        if user_question:
            if not api_key:
                st.warning("Potens.ai API 키를 입력해주세요.")
            else:
                with st.spinner("답변을 생성 중입니다..."):
                    # 4. 질문과 유사한 문서 조각(청크) 검색
                    similar_chunks = search_similar_chunks(st.session_state.vectorstore, st.session_state.model, user_question)
                    
                    # 5. 검색된 청크를 바탕으로 AI에게 정확한 답변 요청
                    context = "\n\n---\n\n".join(similar_chunks)
                    answer = get_ai_answer(context, user_question, api_key)
                    
                    # 6. 결과 출력
                    st.write("### AI 답변:")
                    st.info(answer)
                    
                    with st.expander("AI가 답변 근거로 참고한 원문 내용 보기"):
                        st.write(context.replace("\n", "\n\n"))


if __name__ == '__main__':
    main()
