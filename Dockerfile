FROM python:3.12.3

WORKDIR /usr/src/app

COPY requirements.txt .
COPY manage.py .
COPY db.sqlite3 .
COPY cleanslips ./cleanslips
COPY mysite ./mysite

RUN pip install -r requirements.txt

CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]
