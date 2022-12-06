# BTC PARSER

---

## Setup

1. clone project
2. Create .env files `cp .env.example .env`
3. Complete .env with credentials
4. `docker-compose build`
5. `docker-compose up -d`

* If you're launching parser with _Docker_ and using _Redis_ or _Kafka_ on the same server make sure to configure network in _compose_ file

## Description

| variable        | description                                       |
|-----------------|---------------------------------------------------|
| BASE_DIR        | Directory of parser. Change if use without docker |
| REDIS_HOST      | Address of your Redis server                      |
| REDIS_PORT      | Port of your Redis server                         |
| KAFKA_URL       | Address of your Kafka servers. Split by `,`       |
| KAFKA_TX_TOPIC  | Kafka topik to push transactions                  |
| RPC_URL         | Your blockchain URL                               |
| RPC_TESTNET_URL | Your test blockchain URL                          |
| TESTNET         | `True` or `False`                                 |


