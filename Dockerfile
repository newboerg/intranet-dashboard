FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "30", "app:app"]
