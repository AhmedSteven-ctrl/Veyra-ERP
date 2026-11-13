FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# لو collectstatic فشل، البناء يفشل (بدل ما نكتشف المشكلة وقت التشغيل)
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh \
    && python manage.py collectstatic --noinput \
    && useradd --create-home veyra && chown -R veyra /app
USER veyra

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "veyra.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
