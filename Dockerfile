FROM ubuntu:20.04

RUN apt update --fix-missing
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC \
  apt install -y vim git wget curl unzip python3 python3-pip mpich

WORKDIR /root
RUN wget https://github.com/official-stockfish/books/raw/master/cutechess-cli-linux-64bit.zip
RUN unzip cutechess-cli-linux-64bit.zip
RUN mv cutechess-cli /usr/local/bin/
RUN rm cutechess-cli-linux-64bit.zip

RUN wget https://github.com/official-stockfish/books/raw/master/UHO_XXL_+0.90_+1.19.epd.zip
RUN unzip UHO_XXL_+0.90_+1.19.epd.zip
RUN rm UHO_XXL_+0.90_+1.19.epd.zip

COPY requirements.txt .
RUN pip3 install -r requirements.txt

RUN git clone https://github.com/linrock/Stockfish.git /root/stockfish
WORKDIR /root/stockfish
RUN git checkout -t origin/spsa-tune-nnue-scale-opt
WORKDIR /root/stockfish/src
RUN make -j profile-build ARCH=x86-64-bmi2

WORKDIR /root
RUN cp /root/stockfish/src/stockfish /usr/local/bin/

COPY *.py run_nevergrad.sh .
RUN chmod +x run_nevergrad.sh

CMD sleep infinity
