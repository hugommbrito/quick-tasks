FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# RUN pip install python-multipart

COPY main.py .
COPY static/ static/

EXPOSE 8000

CMD ["python", "main.py"]
