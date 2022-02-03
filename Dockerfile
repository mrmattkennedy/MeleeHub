FROM winamd64/python:3.8.2

LABEL image for a very simple flask application

WORKDIR /website

COPY . .

RUN ["pip3", "install", "pipenv"]

RUN ["pipenv", "install"]

RUN ["pip3", "install" "-r" "requirements.txt]

CMD pipenv run python app.py