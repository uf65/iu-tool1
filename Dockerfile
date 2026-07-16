FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# --- UMGEBUNGSVARIABLEN ---
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true
# 🚀 Das Signal für unseren Python-Code:
ENV RUNNING_IN_DOCKER=true

CMD ["streamlit", "run", "app.py"]