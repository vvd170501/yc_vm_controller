from enum import IntEnum
from typing import Optional

from yandexcloud import SDK
from yandex.cloud.compute.v1.instance_pb2 import Instance
from yandex.cloud.compute.v1.instance_service_pb2 import (
    GetInstanceRequest, StartInstanceRequest, StopInstanceRequest,
    StartInstanceMetadata, StopInstanceMetadata,
)
from yandex.cloud.compute.v1.instance_service_pb2_grpc import InstanceServiceStub
from yandex.cloud.operation.operation_pb2 import Operation


Status = IntEnum('Status', Instance.Status.items())


def init_sdk(key: dict) -> SDK:
    return SDK(service_account_key=key)


def get_instance(sdk: SDK, id_: str) -> Instance:
    service = sdk.client(InstanceServiceStub)
    return service.Get(GetInstanceRequest(instance_id=id_))


def start_instance(sdk: SDK, instance: Instance) -> Operation:
    service = sdk.client(InstanceServiceStub)
    return service.Start(StartInstanceRequest(instance_id=instance.id))


def stop_instance(sdk: SDK, instance: Instance) -> Operation:
    service = sdk.client(InstanceServiceStub)
    return service.Stop(StopInstanceRequest(instance_id=instance.id))


def wait_until_started(sdk: SDK, start_op: Operation) -> Instance:
    return sdk.wait_operation_and_get_result(start_op, response_type=Instance, meta_type=StartInstanceMetadata).response


def wait_until_stopped(sdk: SDK, stop_op: Operation) -> None:
    sdk.wait_operation_and_get_result(stop_op, meta_type=StopInstanceMetadata)


def get_ip(instance: Instance) -> str:
    if instance.status != instance.RUNNING:
        return ''
    intfs = instance.network_interfaces
    if not intfs:
        return ''
    return intfs[0].primary_v4_address.one_to_one_nat.address
