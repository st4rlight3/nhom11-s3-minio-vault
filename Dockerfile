FROM python:3.12.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home vault && mkdir /data && chown vault:vault /data
COPY app ./app
COPY bootstrap.py ./bootstrap.py
USER vault
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
