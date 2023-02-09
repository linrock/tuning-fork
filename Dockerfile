FROM ubuntu:20.04

RUN apt update --fix-missing
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC \
  apt install -y vim git wget curl unzip python3 python3-pip mpich

WORKDIR /root
RUN wget https://github.com/official-stockfish/books/raw/master/cutechess-cli-linux-64bit.zip
RUN unzip cutechess-cli-linux-64bit.zip
RUN mv cutechess-cli /usr/local/bin/
RUN rm cutechess-cli-linux-64bit.zip

WORKDIR /root
RUN git clone https://github.com/vondele/nevergrad4sf.git /root/nevergrad4sf

WORKDIR /root/nevergrad4sf
RUN pip3 install "numpy<1.24.0" matplotlib
RUN pip3 install -r requirements.txt

RUN wget https://github.com/official-stockfish/books/raw/master/UHO_XXL_+0.90_+1.19.epd.zip
RUN unzip UHO_XXL_+0.90_+1.19.epd.zip
RUN rm UHO_XXL_+0.90_+1.19.epd.zip

WORKDIR /root
RUN git clone https://github.com/linrock/Stockfish.git /root/stockfish
WORKDIR /root/stockfish
RUN git checkout -t origin/ng-tune-nullmove-search
WORKDIR /root/stockfish/src
RUN make -j build ARCH=x86-64-bmi2

WORKDIR /root/nevergrad4sf
RUN cp /root/stockfish/src/stockfish .
COPY run_nevergrad.sh .
RUN chmod +x run_nevergrad.sh

CMD sleep infinity
