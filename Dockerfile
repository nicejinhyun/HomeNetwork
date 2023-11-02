FROM python:3

WORKDIR /usr/src/app

#RUN python3 -m pip install paho-mqtt
RUN python3 -m pip install -r requirements.txt

COPY . .

CMD [ "python", "./src/HomeController.py" ]