FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    LIBREOFFICE_BIN=soffice

RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice libreoffice-writer fonts-dejavu fonts-liberation fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY ["КП от Кристины.docx", "./КП от Кристины.docx"]
COPY ["КП КАРТАС ШАБЛОН.docx", "./КП КАРТАС ШАБЛОН.docx"]
COPY ["НИТРИНО ШАБЛОН.docx", "./НИТРИНО ШАБЛОН.docx"]

RUN mkdir -p /app/storage/templates /app/storage/generated /app/storage/previews

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
