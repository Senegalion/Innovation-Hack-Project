FROM python:3.12-slim
ARG WITH_DOCLING=0
WORKDIR /app
COPY requirements.txt requirements-docling.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_DOCLING" = "1" ]; then pip install --no-cache-dir -r requirements-docling.txt; fi
COPY app ./app
ENV STORAGE_DIR=/data/files
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
