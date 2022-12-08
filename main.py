import json
import os

import requests
import asyncio
import aiohttp
import logging
from logging.handlers import RotatingFileHandler
from time import sleep
from redis import Redis
from kafka import KafkaProducer


NETWORK = 'BTC'
KAFKA_TOPIC=os.getenv('KAFKA_TX_TOPIC')
BASE_DIR=os.getenv('BASE_DIR')
REDIS_HOST=os.getenv('REDIS_HOST')
REDIS_PORT=int(os.getenv('REDIS_PORT', 6379))
KAFKA_URLS=os.getenv('KAFKA_URL').split(',')
TESTNET=os.getenv('TESTNET', 'False').lower() in ('true', '1', 't')
RPC_TESTNET_URL=os.getenv('RPC_TESTNET_URL')
RPC_PROD_URL=os.getenv('RPC_URL')


log_name = f'{NETWORK.lower()}_parser'
logging.basicConfig(
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(BASE_DIR + f'/logs/{log_name}.log', maxBytes=20000 * 15000, backupCount=10)
    ],
    level=logging.INFO,
    format='[%(asctime)s] [%(pathname)s:%(lineno)d] [%(levelname)s] - %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
)
logger = logging.getLogger('btc_parser')

r = Redis(host=REDIS_HOST, port=REDIS_PORT)

producer = KafkaProducer(bootstrap_servers=KAFKA_URLS, value_serializer=lambda v: json.dumps(v).encode('utf-8'))

RPC_URL= RPC_TESTNET_URL if TESTNET else RPC_PROD_URL


class BtcWorker:
    def __init__(self):
        self.rpc_url = RPC_URL
        self.previous_block_num = r.get('btc_last_block')
        self.headers = {'Content-type': 'application/json'}
        self.requests_in_chunk = 100
        btc_last_block = r.get('btc_last_block')
        self.last_block_num = int(btc_last_block) + 1 if btc_last_block else self.get_latest_block()
        if self.last_block_num is None:
            raise Exception('cannot read last block')

    def consume(self):
        block_number = self.last_block_num
        n = self.requests_in_chunk
        while True:
            try:
                data_block_hash = self.get_block_hash(block_number)
                if data_block_hash is None:
                    sleep(60)
                else:
                    logger.info(f'new block: {block_number}')
                    data_txs = self.get_tx_in_block(data_block_hash, block_number)
                    if data_txs is None:
                        raise Exception(f'get_tx_in_block error')
                    new_tx = [member.decode("utf-8") for member in  r.smembers('btc_new_tx')]
                    if new_tx is not None:
                        data_txs = new_tx + data_txs
                    if data_txs is not None:
                        chunks = [data_txs[i:i + n] for i in range(0, len(data_txs), n)]
                        txs_count = len(data_txs)
                        txs_consumed = 0
                        for chunk in chunks:
                            data_txs_detail = asyncio.run(self.get_tx_details(chunk, data_block_hash))
                            logger.info(f'block parsed len: {len(data_txs_detail)}')
                            for data in data_txs_detail:
                                if data['error'] is not None:
                                    logger.error(data)
                                else:
                                    for vout in data['result']['vout']:
                                        if vout['scriptPubKey']['type'].lower() != 'nulldata':
                                            try:
                                                if 'addresses' in vout['scriptPubKey']:
                                                    to_address = vout['scriptPubKey']['addresses'][0]
                                                elif 'address' in vout['scriptPubKey']:
                                                    to_address = vout['scriptPubKey']['address']
                                                else:
                                                    continue
                                                tx_data = {
                                                    "txid": data['result']['txid'],
                                                    "value": vout['value'],
                                                    "hex": vout['scriptPubKey']['hex'],
                                                    "to_address": to_address,
                                                    "confirmations": data['result']['confirmations'],
                                                    "block_number": block_number,
                                                    "block_hash": data_block_hash,
                                                    "decimal": 12,
                                                    "network": 'BTC',
                                                    "currency": 'BTC',
                                                    # "status": 'confirmed'
                                                }
                                                r.srem('btc_new_tx', tx_data['txid'])
                                                producer.send(KAFKA_TOPIC, tx_data)
                                            except Exception as e:
                                                logger.error(e)
                            txs_consumed = txs_consumed + len(chunk)
                            logger.info(f'{txs_consumed}/{txs_count} transactions consumed from block {data_block_hash}')
                        r.set('btc_last_block', block_number)
                        block_number = block_number + 1
            except Exception as e:
                logger.error(e)

    def rpc_request(self, method, params):
        response = requests.post(self.rpc_url, json=self._get_payload(method, params), headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(response.text)
        return None

    @staticmethod
    def _get_payload(method, params):
        return {
            "jsonrpc": "1.0",
            "method": method,
            "params": params,
            "id": 1
        }

    def get_latest_block(self):
        response = self.rpc_request('getblockchaininfo', [])
        if response:
            return response['result']['blocks']
        return None

    def get_block_hash(self, data_block_num):
        response = self.rpc_request('getblockhash', [data_block_num])
        if response:
            return response['result']
        return None

    def get_tx_in_block(self, data_block_hash, data_block_num):
        if data_block_num != self.previous_block_num:
            response = self.rpc_request('getblock', [data_block_hash])
            if response:
                return response['result']['tx']
        return None

    async def get_tx_details(self, txs, block_hash):
        txs_details = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in txs:
                # payload = self._get_payload('getrawtransaction', [i, True, block_hash])
                payload = self._get_payload('getrawtransaction', [i, True])
                tasks.append(session.post(self.rpc_url, json=payload, headers=self.headers, ssl=False))
            responses = await asyncio.gather(*tasks)
            for response in responses:
                if response.status == 200:
                    data = await response.json()
                    # logger.info(data)
                    txs_details.append(data)
                else:
                    logger.error(f'error on "getrawtransaction". status code:{response.status}')
            sleep(5)
        return txs_details

def main():
    BtcWorker().consume()

if __name__ == '__main__':
    main()