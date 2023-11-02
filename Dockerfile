FROM python:3

WORKDIR /usr/src/app

#RUN python3 -m pip install paho-mqtt
#RUN python3 -m pip install -r requirements.txt
RUN python3 -m pip install flask
RUN python3 -m pip install flask_wtf
RUN python3 -m pip install flask_moment
RUN python3 -m pip install flask_httpauth
RUN python3 -m pip install flask_bootstrap
RUN python3 -m pip install werkzeug
RUN python3 -m pip install paho-mqtt
RUN python3 -m pip install pyserial
RUN python3 -m pip install requests
RUN python3 -m pip install beautifulsoup4
RUN python3 -m pip install regex
RUN python3 -m pip install pyOpenSSL

COPY . .

CMD [ "python", "./src/Home.py" ]