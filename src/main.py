#!/usr/bin/env python3

import json
import logging
from dataclasses import dataclass
from functools import wraps
from traceback import format_exc
from typing import Optional

import yaml
from grpc._channel import _InactiveRpcError
from telegram import Update
from telegram.ext import CallbackContext, CommandHandler, Filters, MessageHandler, Updater
from telegram.utils.helpers import escape_markdown

from yc_api import (
    Operation,
    Status,
    init_sdk,
    get_instance, start_instance, stop_instance,
    wait_until_started, wait_until_stopped,
    get_ip
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)
logger = logging.getLogger(__name__)  # log rotation?


@dataclass
class Config:
    token: str
    whitelist: list[int]
    notify_cid: Optional[int] = None


def restricted_cmd(method):

    @wraps(method)
    def wrapper(*args, **kwargs):
        self, update = args[:2]
        uid = update.effective_user.id
        if uid not in self.whitelist:
            logger.warning(f'Unauthorized command from user {uid}')
            return
        return method(*args, **kwargs)

    return wrapper


def get_error_str(e: Exception):
    UNKNOWN_ERROR = 'An unknown error occured'
    if not isinstance(e, _InactiveRpcError):
        logger.error(format_exc())
        return UNKNOWN_ERROR
    details = e.details()
    if (
        details.startswith('invalid instance id') or
        details.startswith('The instance') and details.endswith('not found')
    ):
        return 'Invalid instance id'
    logger.error(format_exc())
    return UNKNOWN_ERROR


class Bot:
    def __init__(self, config: Config, sdk_key: dict):
        self._config = config
        self._sdk = init_sdk(sdk_key)
        self._updater = Updater(self._config.token)
        self._updater.dispatcher.add_handler(CommandHandler('start', self.start_cmd, Filters.chat_type.private))
        self._updater.dispatcher.add_handler(CommandHandler('status', self.status, Filters.chat_type.private))
        self._updater.dispatcher.add_handler(CommandHandler('get_ip', self.get_ip, Filters.chat_type.private))
        self._updater.dispatcher.add_handler(CommandHandler('start_vm', self.start_vm, Filters.chat_type.private))
        self._updater.dispatcher.add_handler(CommandHandler('stop_vm', self.stop_vm, Filters.chat_type.private))
        self._updater.dispatcher.add_handler(MessageHandler(Filters.chat_type.private & Filters.command, self.unknown_cmd))

    def start(self):
        self._updater.start_polling()
        self._updater.idle()

    @property
    def whitelist(self):
        return self._config.whitelist

    @restricted_cmd
    def start_cmd(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        context.bot.send_message(cid, 'Available commands: /status, /get_ip, /start_vm, /stop_vm')

    @restricted_cmd
    def unknown_cmd(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        context.bot.send_message(cid, 'Unknown command. Available commands: /status, /get_ip, /start_vm, /stop_vm')

    @restricted_cmd
    def status(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        if context.args:
            inst_id = context.args[0]
        else:
            context.bot.send_message(cid, 'Usage: /status INSTANCE_ID')
            return  # TODO move arg handling to a decorator?
        try:
            inst = get_instance(self._sdk, inst_id)
        except Exception as e:
            context.bot.send_message(cid, get_error_str(e))
            return
        context.bot.send_message(cid, f'Status: {Status(inst.status).name}')

    @restricted_cmd
    def get_ip(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        if context.args:
            inst_id = context.args[0]
        else:
            context.bot.send_message(cid, 'Usage: /get_ip INSTANCE_ID')
            return
        try:
            inst = get_instance(self._sdk, inst_id)
        except Exception as e:
            context.bot.send_message(cid, get_error_str(e))
            return
        if inst.status != Status.RUNNING:
            context.bot.send_message(cid, 'VM is not running')
            return
        context.bot.send_message(cid, self._ip_str(get_ip(inst)))

    @restricted_cmd
    def start_vm(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        if context.args:
            inst_id = context.args[0]
        else:
            context.bot.send_message(cid, 'Usage: /start_vm INSTANCE_ID')
            return
        try:
            inst = get_instance(self._sdk, inst_id)
        except Exception as e:
            context.bot.send_message(cid, get_error_str(e))
            return
        if inst.status == Status.RUNNING:
            context.bot.send_message(cid, 'VM is already running')
            return
        if inst.status == Status.PROVISIONING:
            context.bot.send_message(cid, 'VM is already starting')
            return
        try:
            op = start_instance(self._sdk, inst)
        except Exception as e:
            context.bot.send_message(cid, 'An error occured, maybe the instance is already running')
            return
        context.bot.send_message(cid, 'VM is starting...')
        self._updater.dispatcher.run_async(self._wait_for_start, op, cid, inst_id)
        self._notify(inst_id, 'started')

    @restricted_cmd
    def stop_vm(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        if context.args:
            inst_id = context.args[0]
        else:
            context.bot.send_message(cid, 'Usage: /stop_vm INSTANCE_ID')
            return
        try:
            inst = get_instance(self._sdk, inst_id)
        except Exception as e:
            context.bot.send_message(cid, get_error_str(e))
            return
        if inst.status == Status.STOPPED:
            context.bot.send_message(cid, 'VM is already stopped')
            return
        if inst.status == Status.STOPPING:
            context.bot.send_message(cid, 'VM is already stopping')
            return
        try:
            op = stop_instance(self._sdk, inst)
        except Exception as e:
            context.bot.send_message(cid, 'An unknown error occured')
            return
        context.bot.send_message(cid, 'VM is stopping...')
        self._updater.dispatcher.run_async(self._wait_for_stop, op, cid, inst_id)
        self._notify(inst_id, 'stopped')

    def _notify(self, inst_id: str, action: str):
        cid = self._config.notify_cid
        if cid is None:
            return
        self._updater.bot.send_message(cid, f'⚠️ `{inst_id}` was {action}', parse_mode='MarkdownV2')

    def _ip_str(self, ip: str) -> str:
        return f'IP: {ip}' if ip else 'No external IP'

    def _wait_for_start(self, op: Operation, cid: int, inst_id: str):
        try:
            inst = wait_until_started(self._sdk, op)
        except Exception as e:
            self._updater.bot.send_message(cid, f'An unknown error occured while starting `{inst_id}`', parse_mode='MarkdownV2')
            return
        if inst.status != Status.RUNNING:
            self._updater.bot.send_message(cid, f'`{inst_id}` failed to start or was stopped', parse_mode='MarkdownV2')
            return
        ip_str = escape_markdown(self._ip_str(get_ip(inst)), version=2)
        self._updater.bot.send_message(cid, f'`{inst_id}` is now running \({ip_str}\)', parse_mode='MarkdownV2')

    def _wait_for_stop(self, op: Operation, cid: int, inst_id: str):
        try:
            wait_until_stopped(self._sdk, op)
        except Exception as e:
            self._updater.bot.send_message(cid, f'An unknown error occured while stopping `{inst_id}`', parse_mode='MarkdownV2')
            return
        self._updater.bot.send_message(cid, f'Stopped `{inst_id}`', parse_mode='MarkdownV2')


def main() -> None:
    with open('/config/bot_config.yaml') as f:
        raw_cfg = yaml.safe_load(f)
    config = Config(**raw_cfg)
    with open('/config/key.json') as f:
        key = json.load(f)

    bot = Bot(config, key)
    bot.start()


if __name__ == '__main__':
    main()
