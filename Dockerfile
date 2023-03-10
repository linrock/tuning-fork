FROM ubuntu:20.04

RUN apt-get update --fix-missing
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC \
  apt install -y vim git tig wget curl unzip jq python3 python3-pip mpich

WORKDIR /tmp
RUN wget https://github.com/official-stockfish/books/raw/master/cutechess-cli-linux-64bit.zip
RUN unzip cutechess-cli-linux-64bit.zip
RUN mv cutechess-cli /usr/local/bin/

RUN wget https://github.com/official-stockfish/books/raw/master/UHO_XXL_+0.90_+1.19.epd.zip
RUN unzip UHO_XXL_+0.90_+1.19.epd.zip
RUN mv UHO_XXL_+0.90_+1.19.epd /root/

WORKDIR /root
COPY .bash_profile .
RUN echo 'source ~/.bash_profile' >> .bashrc

COPY requirements.txt .
RUN pip3 install -r requirements.txt

RUN git clone https://github.com/official-stockfish/Stockfish.git /root/stockfish
WORKDIR /root/stockfish/src
RUN make -j profile-build ARCH=x86-64-bmi2
RUN ln -s /root/stockfish/src/stockfish /usr/local/bin/

WORKDIR /root
COPY *.py *.sh .
COPY stats stats
RUN chmod +x *.sh
RUN mkdir experiments

# if ssh keys are present, set up ssh for mpi workers
# RUN mkdir /root/.ssh
# COPY id_ed25519* /root/.ssh/
# COPY id_ed25519.pu* /root/.ssh/authorized_keys
# RUN chmod 600 /root/.ssh/*

CMD sleep infinity
