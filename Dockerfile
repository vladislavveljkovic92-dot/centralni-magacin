FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY magacin_backend ./magacin_backend
COPY migrations ./migrations
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY alembic.ini manage.py streamlit_app.py start_server.py ./
RUN useradd --create-home app && chown -R app:app /app
USER app
EXPOSE 8501
CMD ["python", "start_server.py"]

