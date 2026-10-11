FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
ARG CHATARCHIVE_PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --require-hashes --index-url "$CHATARCHIVE_PIP_INDEX_URL" -r requirements.lock && useradd --system --uid 10001 --create-home chatarchive
COPY chatarchive ./chatarchive
COPY scripts/export_chatlog.py ./scripts/export_chatlog.py
COPY web ./web
COPY examples ./examples
RUN mkdir /data && chown chatarchive:chatarchive /data
USER chatarchive
ENV CHATARCHIVE_DATA=/data
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8769
CMD ["python","-m","uvicorn","chatarchive.server:app","--host","0.0.0.0","--port","8769","--no-access-log","--no-proxy-headers"]
