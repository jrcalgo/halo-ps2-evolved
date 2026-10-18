FROM ubuntu@sha256:a2d43bffc46670d7108bb3c0468c67c5557c4c92e83e1e34cbff1322ad1b94dc
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends gcc-12=12.4.0-2ubuntu1~24.04.1 g++-12=12.4.0-2ubuntu1~24.04.1 make=4.3-4.1build2 cmake=3.28.3-1build7 git=1:2.43.0-1ubuntu7.3 python3=3.12.3-0ubuntu2.1 perl=5.38.2-3.2ubuntu0.6 m4=1.4.19-4build1 zlib1g-dev=1:1.3.dfsg-3.1ubuntu2.2 patch=2.7.6-7build3 && rm -rf /var/lib/apt/lists/*
RUN ln -s /usr/bin/gcc-12 /usr/local/bin/gcc && ln -s /usr/bin/gcc-12 /usr/local/bin/cc && ln -s /usr/bin/g++-12 /usr/local/bin/g++ && ln -s /usr/bin/g++-12 /usr/local/bin/c++
