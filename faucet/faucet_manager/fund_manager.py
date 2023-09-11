import time
import os
import logging
from django.core.cache import cache
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from faucet.faucet_manager.fund_manager_abi import manager_abi
from faucet.models import Chain, BrightUser, LightningConfig
from faucet.helpers import memcache_lock
from faucet.constants import *
from solana.rpc.api import Client
from solana.rpc.core import RPCException, RPCNoResultException
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction_status import TransactionConfirmationStatus
from .anchor_client.accounts.lock_account import LockAccount
from .anchor_client import instructions
from .solana_client import SolanaClient
from .lnpay_client import LNPayClient


class FundMangerException:
    class GasPriceTooHigh(Exception):
        pass

    class RPCError(Exception):
        pass


class EVMFundManager:
    def __init__(self, chain: Chain):
        self.chain = chain
        self.abi = manager_abi

    @property
    def w3(self) -> Web3:
        assert self.chain.rpc_url_private is not None
        try:
            _w3 = Web3(Web3.HTTPProvider(self.chain.rpc_url_private))
            if self.chain.poa:
                _w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            if _w3.isConnected():
                _w3.eth.set_gas_price_strategy(rpc_gas_price_strategy)
                return _w3
        except Exception as e:
            logging.error(e)
            raise FundMangerException.RPCError(
                f"Could not connect to rpc {self.chain.rpc_url_private}"
            )

    @property
    def is_gas_price_too_high(self):
        try:
            gas_price = self.w3.eth.gas_price
            print(f"Gas price: {gas_price} vs max: {self.chain.max_gas_price}")
            if gas_price > self.chain.max_gas_price:
                return True
            return False
        except Exception as e:
            logging.error(e)
            return True

    @property
    def account(self) -> LocalAccount:
        return self.w3.eth.account.privateKeyToAccount(self.chain.wallet.main_key)

    @staticmethod
    def to_checksum_address(address: str):
        return Web3.toChecksumAddress(address.lower())

    def get_fund_manager_checksum_address(self):
        return self.to_checksum_address(self.chain.fund_manager_address)

    @property
    def contract(self):
        return self.w3.eth.contract(address=self.get_fund_manager_checksum_address(), abi=self.abi)

    def transfer(self, bright_user: BrightUser, amount: int):
        tx = self.single_eth_transfer_signed_tx(amount, bright_user.address)
        try:
            self.w3.eth.send_raw_transaction(tx.rawTransaction)
            return tx["hash"].hex()
        except Exception as e:
            raise FundMangerException.RPCError(str(e))

    def multi_transfer(self, data):
        tx = self.multi_eth_transfer_signed_tx(data)
        try:
            self.w3.eth.send_raw_transaction(tx.rawTransaction)
            return tx["hash"].hex()
        except Exception as e:
            raise FundMangerException.RPCError(str(e))

    def single_eth_transfer_signed_tx(self, amount: int, to: str):
        tx_function = self.contract.functions.withdrawEth(amount, to)
        return self.prepare_tx_for_broadcast(tx_function)

    def multi_eth_transfer_signed_tx(self, data):
        tx_function = self.contract.functions.multiWithdrawEth(data)
        return self.prepare_tx_for_broadcast(tx_function)

    def prepare_tx_for_broadcast(self, tx_function):
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        gas_estimation = tx_function.estimateGas({"from": self.account.address})
        if self.chain.chain_id == "997":
            gas_estimation = 100000

        if self.is_gas_price_too_high:
            raise FundMangerException.GasPriceTooHigh("Gas price is too high")

        tx_data = tx_function.buildTransaction(
            {
                "nonce": nonce,
                "from": self.account.address,
                "gas": gas_estimation,
                "gasPrice": int(self.w3.eth.gas_price * self.chain.gas_multiplier),
            }
        )
        signed_tx = self.w3.eth.account.sign_transaction(tx_data, self.account.key)
        return signed_tx

    def is_tx_verified(self, tx_hash):
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] == 1:
            return True
        return False

    def get_tx(self, tx_hash):
        tx = self.w3.eth.get_transaction(tx_hash)
        return tx

    def from_wei(self, value: int, unit: str = 'ether'):
        return self.w3.fromWei(value, unit)


class SolanaFundManager:
    def __init__(self, chain: Chain):
        self.chain = chain
        self.abi = manager_abi

    @property
    def w3(self) -> Client:
        assert self.chain.rpc_url_private is not None
        try:
            _w3 = Client(self.chain.rpc_url_private)
            if _w3.is_connected():
                return _w3
        except Exception as e:
            logging.error(e)
            raise FundMangerException.RPCError(
                f"Could not connect to rpc {self.chain.rpc_url_private}"
            )

    @property
    def account(self) -> Keypair:
        return Keypair.from_base58_string(self.chain.wallet.main_key)

    @property
    def program_id(self) -> Pubkey:
        return Pubkey.from_string(self.chain.fund_manager_address)

    @property
    def lock_account_seed(self) -> bytes:
        return bytes("locker", "utf-8")

    @property
    def lock_account_address(self) -> Pubkey:
        lock_account_address, nonce = Pubkey.find_program_address(
            [self.lock_account_seed], self.program_id
        )
        return lock_account_address

    @property
    def lock_account(self) -> LocalAccount:
        lock_account_info = self.w3.get_account_info(self.lock_account_address)
        if lock_account_info.value:
            return LockAccount.decode(lock_account_info.value.data)
        return None

    @property
    def is_initialized(self):
        if self.lock_account:
            return self.lock_account.initialized
        return False

    @property
    def owner(self):
        if self.lock_account:
            return self.lock_account.owner
        return None

    @property
    def operator(self):
        if self.lock_account:
            return self.lock_account.operator
        return None

    @property
    def solana_client(self):
        return SolanaClient(self.w3, self.account)

    def is_gas_price_too_high(self, instruction):
        if isinstance(instruction, list):
            txn = Transaction().add(*instruction)
        else:
            txn = Transaction().add(instruction)
        try:
            fee = self.w3.get_fee_for_message(txn.compile_message()).value
            if not fee:
                fee = 5000
            if fee > self.chain.max_gas_price:
                return True
            return False
        except Exception as ex:
            logging.warning(ex)
            return True

    def multi_transfer(self, data):
        if self.is_initialized:
            instruction = [
                instructions.withdraw(
                    {"amount": item['amount']},
                    {
                        "lock_account": self.lock_account_address,
                        "operator": self.operator,
                        "recipient": Pubkey.from_string(item["to"])
                    },
                    self.program_id
                ) for item in data
            ]
            if self.is_gas_price_too_high(instruction):
                raise FundMangerException.GasPriceTooHigh()
            signature = self.solana_client.call_program(instruction)
            if not signature:
                raise Exception("Transferring lamports to the receivers failed")
            return str(signature)
        else:
            raise Exception("The program is not initialized yet")

    def is_tx_verified(self, tx_hash):
        try:
            confirmation_status = (
                self.w3.get_signature_statuses([Signature.from_string(tx_hash)])
                .value[0]
                .confirmation_status
            )
            return confirmation_status in [
                TransactionConfirmationStatus.Confirmed,
                TransactionConfirmationStatus.Finalized,
            ]
        except RPCException:
            logging.warning(
                "Solana raised the RPCException at get_signature_statuses()"
            )
            return False
        except RPCNoResultException:
            logging.warning(
                "Solana raised the RPCNoResultException at get_signature_statuses()"
            )
            return False
        except Exception:
            raise


class LightningFundManager:
    def __init__(self, chain: Chain):
        self.chain = chain

    @property
    def config(self) -> LightningConfig:
        config = LightningConfig.objects.first()
        assert config is not None, "There is no Lightning config"
        return config

    @property
    def api_key(self):
        return self.chain.wallet.main_key

    @property
    def lnpay_client(self):
        return LNPayClient(
            self.chain.rpc_url_private, self.api_key, self.chain.fund_manager_address
        )

    def __check_max_cap_exceeds(self, amount) -> bool:
        try:
            config = self.config
            active_round = int(int(time.time()) / config.period) * config.period
            if active_round != config.current_round:
                config.claimed_amount = 0
                config.current_round = active_round
                config.save()

            return config.claimed_amount + amount > config.period_max_cap
        except Exception as ex:
            logging.error(ex)
            return True

    def multi_transfer(self, data):
        client = self.lnpay_client

        with memcache_lock(MEMCACHE_LIGHTNING_LOCK_KEY, os.getpid()) as acquired:
            assert acquired, "Could not acquire Lightning multi-transfer lock"

            item = data[0]
            assert not self.__check_max_cap_exceeds(
                item["amount"]
            ), "Lightning periodic max cap exceeded"
            try:
                pay_result = client.pay_invoice(item["to"])

                if pay_result:
                    result = pay_result["lnTx"]["id"]

                    config = self.config
                    config.claimed_amount += item["amount"]
                    config.save()

                    cache.delete(MEMCACHE_LIGHTNING_LOCK_KEY)

                    return result
                else:
                    raise Exception("Lightning: Could not pay the invoice")
            except Exception as exc:
                cache.delete(MEMCACHE_LIGHTNING_LOCK_KEY)
                raise exc

    def is_tx_verified(self, tx_hash):
        invoice_status = self.lnpay_client.get_invoice_status(tx_hash)
        return invoice_status["settled"] == 1
