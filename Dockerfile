FROM ubuntu:20.04

RUN apt update --fix-missing
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC \
  apt install -y vim git wget curl unzip python3 python3-pip mpich

WORKDIR /root
RUN mkdir books
RUN git clone https://github.com/vondele/nevergrad4sf.git /root/nevergrad4sf
RUN git clone https://github.com/official-stockfish/Stockfish.git /root/stockfish

WORKDIR /root/nevergrad4sf
RUN pip3 install "numpy<1.24.0" matplotlib
RUN pip3 install -r requirements.txt

WORKDIR /root/books
RUN wget https://github.com/official-stockfish/books/raw/master/UHO_XXL_+0.90_+1.19.epd.zip
RUN unzip UHO_XXL_+0.90_+1.19.epd.zip
RUN rm UHO_XXL_+0.90_+1.19.epd.zip

WORKDIR /root
RUN wget https://github.com/official-stockfish/books/raw/master/cutechess-cli-linux-64bit.zip
RUN unzip cutechess-cli-linux-64bit.zip
RUN mv cutechess-cli /usr/local/bin/
RUN rm cutechess-cli-linux-64bit.zip

WORKDIR /root/nevergrad4sf
RUN ln -s ../books/UHO_XXL_+0.90_+1.19.epd .
COPY run_nevergrad.sh .

CMD sleep infinity
