#
FROM python:3.8.5

#
WORKDIR /code

#
COPY ./requirements.txt /code/requirements.txt
#
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

#
COPY ./app /code/app
COPY ./app/static /code/static
EXPOSE 8080 8000
#
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

# docker build -t go-fastapi . (names image and stores it)
# docker run -d --name go-fastapi -p 8000:8000 go-fastapi  (expose ports and name the container)
# docker rm go-fastapi (removes image)
# docker port go-fastapi (see the port mapping)

# regular run:
# poetry run uvicorn --reload app.main:app