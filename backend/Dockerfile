FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home app
# Linux checkouts may use umask 077. Keep copied files readable by the runtime
# user without depending on the source checkout's permissions.
COPY --chown=app:app app ./app
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app entrypoint.sh ./entrypoint.sh
COPY --chown=app:app tests ./tests
RUN chmod u+x /app/entrypoint.sh
USER app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
CMD ["/bin/sh", "/app/entrypoint.sh"]
