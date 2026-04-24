# 운영 가이드

## 빠른 명령어 참조

```bash
# ── 최초 설치 ─────────────────────────────────────────────────────────────
py -3.11 -m venv venv                        # 가상환경 생성 (최초 1회)
venv\Scripts\pip install -r requirements.txt  # 의존성 설치 (최초 1회 / 업데이트 시)

# ── PDF 인제스트 (Pinecone 업로드) ───────────────────────────────────────
# rag_data\ 폴더에 PDF 파일을 복사한 뒤 실행
venv\Scripts\python ingest.py                        # rag_data\ 전체 인덱싱
venv\Scripts\python ingest.py --dir rag_data         # 동일 (기본값 명시)
venv\Scripts\python ingest.py --dir path\to\pdfs     # 다른 폴더 지정

# 특징:
#   - 이미 인덱싱된 파일은 MD5 해시로 자동 감지 후 스킵 (멱등성)
#   - 새 PDF만 추가 처리됨 → 기존 인덱스 손상 없음

# ── 앱 실행 ─────────────────────────────────────────────────────────────
venv\Scripts\streamlit run app.py                    # 개발 서버 (브라우저 자동 오픈)
venv\Scripts\streamlit run app.py --server.port 8502 # 포트 변경
venv\Scripts\streamlit run app.py --server.headless true  # UI 없는 서버 환경

# ── 테스트 ──────────────────────────────────────────────────────────────
venv\Scripts\pytest tests/ -v                        # 전체 테스트
venv\Scripts\pytest tests/test_ingest.py -v          # 인제스트 테스트만
venv\Scripts\pytest tests/test_rag.py -v             # RAG 테스트만
```

---

## 배포 방법 비교

| 방법 | 비용 | 난이도 | 팀 공유 | 세션 유지 | 추천 대상 |
|------|------|--------|---------|----------|----------|
| 로컬 실행 | 무료 | ⭐ | ✗ | ✓ | 단독 연구자 |
| Streamlit Community Cloud | 무료 | ⭐⭐ | ✓ | △ | 소규모 연구팀 |
| Hugging Face Spaces | 무료 | ⭐⭐ | ✓ | △ | AI 연구팀 |
| Render / Railway | 무료~유료 | ⭐⭐⭐ | ✓ | ✓ | 팀 운영 서버 |
| Docker + VPS | 저렴 | ⭐⭐⭐⭐ | ✓ | ✓ | 기관 내부망 |

> **세션 유지 △**: 앱 재시작 시 `data/sessions/` 초기화. Pinecone 인덱스(문서 검색)는 영구 유지됨.

---

## 방법 1. Streamlit Community Cloud (무료, 추천)

Next.js + Vercel과 가장 유사한 방식. GitHub 레포를 연결하면 자동 배포됩니다.

### 전제 조건
- GitHub 레포 (public 또는 private 모두 가능)
- Pinecone 인덱스에 이미 데이터 인제스트 완료 (로컬에서 실행)

### PDF 인제스트는 배포 전 로컬에서 실행
```
PDF 파일 → (로컬) python ingest.py → Pinecone 클라우드 저장
→ 앱 배포 (PDF 불필요, Pinecone에서 직접 검색)
```
배포된 앱은 PDF 파일 없이 Pinecone에서만 검색하므로 파일 업로드가 필요 없습니다.

### 배포 절차

**1. `.gitignore` 확인 — `.env` 와 `rag_data/` 제외**
```
.env
rag_data/
venv/
data/sessions/
logs/
```

**2. GitHub에 레포 생성 및 push**
```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin master
```

**3. Streamlit Community Cloud 접속**
- https://share.streamlit.io → GitHub 로그인
- **New app** → 레포 선택 → Main file path: `app.py` → Deploy

**4. API 키 등록 (Secrets)**
- 배포 후 앱 대시보드 → ⋮ → **Settings** → **Secrets**
- 아래 내용 입력:
```toml
OPENAI_API_KEY = "sk-proj-..."
PINECONE_API_KEY = "pcsk_..."
```

**5. 완료**
- `https://YOUR_APP.streamlit.app` 으로 접속
- GitHub main 브랜치 push 시 자동 재배포

### 제한사항
- 메모리 1GB (대용량 PDF 인제스트 불가 → 로컬에서 인제스트 후 배포)
- `data/sessions/` 파일은 앱 재시작 시 초기화 (Streamlit 에피머럴 파일시스템)
- 월 1,000시간 무료 (초과 시 슬립)

---

## 방법 2. Hugging Face Spaces (무료, AI 친화)

AI/ML 연구자들에게 익숙한 플랫폼. Streamlit 네이티브 지원.

### 배포 절차

**1. Space 생성**
- https://huggingface.co/new-space
- SDK: **Streamlit** 선택
- Visibility: Private (연구 데이터 보호 권장)

**2. 파일 업로드**
```bash
# HF CLI 설치
pip install huggingface_hub

# 로그인
huggingface-cli login

# 파일 업로드 (venv, rag_data, .env 제외)
huggingface-cli upload YOUR_USERNAME/YOUR_SPACE . . \
  --ignore-patterns "venv/*" "rag_data/*" ".env" "data/*" "logs/*"
```

**3. API 키 등록**
- Space 설정 → **Variables and secrets**
- `OPENAI_API_KEY`, `PINECONE_API_KEY` 등록

**4. `packages.txt` 추가 (시스템 패키지 필요 시)**
```
# 루트에 packages.txt 생성 (보통 불필요)
```

### 특징
- 무료 CPU 인스턴스 제공
- Private Space는 팀원 초대 가능
- GPU 업그레이드 가능 (유료)

---

## 방법 3. Render (무료 → 유료, 팀 서버)

지속적 스토리지가 필요한 팀 운영 서버. `data/sessions/` 영구 보존 가능.

### 배포 절차

**1. `render.yaml` 생성** (프로젝트 루트)
```yaml
services:
  - type: web
    name: research-rag
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: streamlit run app.py --server.port $PORT --server.headless true --server.address 0.0.0.0
    envVars:
      - key: OPENAI_API_KEY
        sync: false          # Render 대시보드에서 직접 입력
      - key: PINECONE_API_KEY
        sync: false
    disk:
      name: sessions-disk
      mountPath: /opt/render/project/src/data
      sizeGB: 1              # 세션 파일 영구 보존
```

**2. Render 접속**
- https://render.com → New → Web Service → GitHub 레포 연결
- 환경변수 입력 후 Deploy

### 비용
- 무료 플랜: 월 750시간, 15분 비활성 시 슬립, 디스크 없음
- Starter ($7/월): 슬립 없음, 디스크 포함 → 운영 추천

---

## 방법 4. Docker (기관 내부망 / 온프레미스)

인터넷 연결이 제한된 기관 서버나 내부망 배포에 적합.

### `Dockerfile` 생성
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/sessions logs

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
```

### 빌드 및 실행
```bash
# 이미지 빌드
docker build -t research-rag .

# 실행 (세션 파일 호스트에 마운트)
docker run -d \
  --name research-rag \
  -p 8501:8501 \
  -e OPENAI_API_KEY="sk-proj-..." \
  -e PINECONE_API_KEY="pcsk_..." \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  research-rag

# 접속
open http://localhost:8501

# 로그 확인
docker logs -f research-rag
```

### 내부망 팀 공유
```bash
# 서버 IP로 팀원 접속 허용
docker run -p 0.0.0.0:8501:8501 ... research-rag
# 팀원: http://서버IP:8501
```

### docker-compose.yml (운영 환경)
```yaml
version: "3.9"
services:
  app:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```
```bash
docker compose up -d          # 백그라운드 시작
docker compose down           # 중지
docker compose pull && docker compose up -d  # 업데이트
```

---

## 방법 5. 로컬 → 팀 공유 (ngrok, 임시)

앱을 로컬에서 실행하고 일시적으로 외부 URL 공유.

```bash
# ngrok 설치 후
streamlit run app.py &
ngrok http 8501
# → https://xxxx.ngrok.io 팀 공유 (ngrok 실행 중에만 유효)
```

---

## 배포 후 PDF 추가 절차

배포된 앱은 Pinecone에서 검색하므로, **새 PDF 추가는 항상 로컬에서 인제스트 후 자동 반영**됩니다.

```
1. rag_data\ 에 새 PDF 복사
2. (로컬) venv\Scripts\python ingest.py
   → "처리됨: 1개 파일, 총 청크: N개" 확인
3. 배포된 앱에서 사이드바 "문서 인덱스 업데이트" 클릭
   (또는 앱 재시작 시 자동으로 최신 Pinecone 인덱스 사용)
```

---

## 환경변수 체크리스트

| 변수 | 설명 | 필수 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | ✅ |
| `PINECONE_API_KEY` | Pinecone API 키 | ✅ |

로컬: `.env` 파일
배포: 각 플랫폼 Secrets/Environment Variables 설정
