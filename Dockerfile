FROM python:3

WORKDIR /app
ADD . .
RUN pip3 install -r requirements.txt && chmod +x run.py

CMD ["/app/run.py"]