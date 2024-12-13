import asyncio
import logging
import time
from typing import Literal, Optional, cast

import serial

from pylabrobot.incubators.backend import IncubatorBackend
from pylabrobot.incubators.cytomat.constants import (
  ActionRegister,
  ActionType,
  CytomatActionResponse,
  CytomatIncupationResponse,
  CytomatType,
  ErrorRegister,
  LoadStatusAtProcessor,
  LoadStatusFrontOfGate,
  SensorRegister,
  SwapStationPosition,
  WarningRegister,
)
from pylabrobot.incubators.cytomat.errors import CytomatTelegramStructureError, error_map
from pylabrobot.incubators.cytomat.schemas import (
  ActionRegisterState,
  OverviewRegisterState,
  SensorStates,
  SwapStationState,
)
from pylabrobot.incubators.cytomat.utils import (
  hex_to_base_twelve,
  hex_to_binary,
  validate_storage_location_number,
)
from pylabrobot.incubators.rack import Rack
from pylabrobot.resources.carrier import PlateHolder
from pylabrobot.resources.plate import Plate

logger = logging.getLogger(__name__)


class Cytomat(IncubatorBackend):
  default_baud = 9600
  serial_message_encoding = "utf-8"

  def __init__(self, model: CytomatType, port: str):
    supported_models = [
      CytomatType.C6000,
      CytomatType.C6002,
      CytomatType.C2C_425,
      CytomatType.C2C_450_SHAKE,
      CytomatType.C5C,
    ]
    if model not in supported_models:
      raise NotImplementedError("Only the following Cytomats are supported:", supported_models)
    self.model = model
    self.port = port

  async def setup(self):
    try:
      self.ser = serial.Serial(
        port=self.port,
        baudrate=self.default_baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        write_timeout=1,
        timeout=1,
      )
    except serial.SerialException as e:
      logger.error("Could not connect to cytomat, is it in use by a different notebook?")
      raise e

    await self.wait_for_task_completion()
    await self.initialize()

  async def stop(self):
    if self.ser.is_open:
      self.ser.close()

  def _get_carriage_return(self):
    return "\r" if self.model == CytomatType.C2C_425 else "\r\n"

  def _assemble_command(self, command_type: str, command: str, params: str):
    command = f"{command_type}:{command} {params}".strip() + self._get_carriage_return()
    return command

  async def _send_cmd(self, command_type: str, command: str, params: str, wait: bool = True) -> str:
    command_str = self._assemble_command(command_type=command_type, command=command, params=params)
    logging.debug(command_str.encode(self.serial_message_encoding))
    self.ser.write(command_str.encode(self.serial_message_encoding))
    resp = self.ser.read(128).decode(self.serial_message_encoding)
    if len(resp) == 0:
      raise RuntimeError("Cytomat did not respond to command, is it turned on?")
    key, *values = resp.split()
    value = " ".join(values)

    if key == CytomatActionResponse.OK.value or key == command:
      # actions return an OK response, while checks return the command at the start of the response
      # if wait:
      # TODO: sometimes this command does not get recognized
      # await self.wait_for_task_completion()
      return value
    if key == CytomatActionResponse.ERROR.value:
      logger.error("Command %s failed with: '%s'", command_str, resp)

      if value == "03":
        error_register = await self.get_error_register()
        raise CytomatTelegramStructureError(f"Telegram structure error: {error_register}")
      if int(value, base=16) in error_map:
        raise error_map[int(value, base=16)]
      raise Exception(f"Unknown cytomat error code in response: {resp}")

    logging.error("Command %s recieved an unknown response: '%s'", command_str, resp)
    raise Exception(f"Unknown response from cytomat: {resp}")

  def _site_to_firmware_string(self, site: PlateHolder) -> str:
    rack = cast(Rack, site.parent)
    rack_idx = rack.index
    site_idx = next(idx for idx, s in rack.sites.items() if s == site)

    if self.model in [CytomatType.C2C_425]:
      return f"{str(rack_idx).zfill(2)} {str(site_idx).zfill(2)}"

    if self.model in [
      CytomatType.C6000,
      CytomatType.C6002,
      CytomatType.C2C_450_SHAKE,
      CytomatType.C5C,
    ]:
      slots_to_skip = sum(r.capacity for r in self.racks[:rack_idx])
      if self.model == CytomatType.C2C_450_SHAKE:
        # TODO: is this generally true?
        # This is the "rack shaker" we ripped out ever other level so multiply by two.
        # The initial rack shaker is unused, so add fifteen.
        absolute_slot = 15 + 2 * (slots_to_skip + site_idx)
      else:
        absolute_slot = slots_to_skip + site_idx

      return f"{absolute_slot:03}"

    raise ValueError(f"Unsupported Cytomat model: {self.model}")

  async def get_overview_register(self) -> OverviewRegisterState:
    resp = await self._send_cmd("ch", "bs", "")
    return OverviewRegisterState.from_resp(resp)

  async def get_warning_register(self) -> WarningRegister:
    hex_value = await self._send_cmd("ch", "bw", "")
    for member in WarningRegister:
      if hex_value == member.value:
        return member

    raise Exception(f"Unknown warning register value: {hex_value}")

  async def get_error_register(self) -> ErrorRegister:
    hex_value = await self._send_cmd("ch", "be", "")
    for member in ErrorRegister:
      if hex_value == member.value:
        return member

    raise Exception(f"Unknown error register value: {hex_value}")

  async def reset_error_register(self) -> None:
    await self._send_cmd("rs", "be", "")

  async def initialize(self) -> None:
    """move the cytomat arm to the home position"""
    await self._send_cmd("ll", "in", "")

  async def open_door(self):
    resp = await self._send_cmd("ll", "gp", "002")
    return OverviewRegisterState.from_resp(resp)

  async def close_door(self):
    resp = await self._send_cmd("ll", "gp", "001")
    return OverviewRegisterState.from_resp(resp)

  async def shovel_in(self):
    resp = await self._send_cmd("ll", "sp", "001")
    return OverviewRegisterState.from_resp(resp)

  async def shovel_out(self):
    resp = await self._send_cmd("ll", "sp", "002")
    return OverviewRegisterState.from_resp(resp)

  async def get_action_register(self) -> ActionRegisterState:
    hex_value = await self._send_cmd("ch", "ba", "")
    binary_repr = hex_to_binary(hex_value)
    target, action = binary_repr[:3], binary_repr[3:]

    target_enum = None
    for action_type_member in ActionType:
      if int(target, 2) == int(action_type_member.value, 16):
        target_enum = action_type_member
        break
    assert target_enum is not None, f"Unknown target value: {target}"

    action_enum = None
    for action_register_member in ActionRegister:
      if int(action, base=2) == int(action_register_member.value, base=16):
        action_enum = action_register_member
        break
    assert action_enum is not None, f"Unknown HIGH_LEVEL_COMMANDment value: {action}"

    return ActionRegisterState(target=target_enum, action=action_enum)

  async def get_swap_register(self) -> SwapStationState:
    value = await self._send_cmd("ch", "sw", "")

    return SwapStationState(
      position=SwapStationPosition(int(value[0])),
      load_status_front_of_gate=LoadStatusFrontOfGate(int(value[1])),
      load_status_at_processor=LoadStatusAtProcessor(int(value[2])),
    )

  async def get_sensor_register(self) -> SensorStates:
    hex_value = await self._send_cmd("ch", "ts", "")
    binary_values = hex_to_base_twelve(hex_value)
    return SensorStates(
      **{member.name: bool(int(binary_values[member.value])) for member in SensorRegister}
    )

  async def action_transfer_to_storage(  # used by insert_plate
    self, site: PlateHolder
  ) -> OverviewRegisterState:
    # Open lift door, retrieve from transfer, close door, place at storage
    resp = await self._send_cmd("mv", "ts", self._site_to_firmware_string(site))
    return OverviewRegisterState.from_resp(resp)

  async def action_storage_to_transfer(  # used by retrieve_plate
    self, site: PlateHolder
  ) -> OverviewRegisterState:
    # Retrieve from storage, open door, move to transfer, close door
    resp = await self._send_cmd("mv", "st", self._site_to_firmware_string(site))
    return OverviewRegisterState.from_resp(resp)

  async def action_storage_to_wait(self, site: PlateHolder) -> OverviewRegisterState:
    # Retrieve from storage, move to wait position
    resp = await self._send_cmd("mv", "sw", self._site_to_firmware_string(site))
    return OverviewRegisterState.from_resp(resp)

  async def action_wait_to_storage(self, site: PlateHolder) -> OverviewRegisterState:
    # Move from wait to storage, unload, return to wait
    resp = await self._send_cmd("mv", "ws", self._site_to_firmware_string(site))
    return OverviewRegisterState.from_resp(resp)

  async def action_wait_to_transfer(self) -> OverviewRegisterState:
    # Open door, place on transfer, return to wait, close door
    resp = await self._send_cmd("mv", "wt", "")
    return OverviewRegisterState.from_resp(resp)

  async def action_transfer_to_wait(self) -> OverviewRegisterState:
    # Open door, retrieve from transfer, return to wait, close door
    resp = await self._send_cmd("mv", "tw", "")
    return OverviewRegisterState.from_resp(resp)

  async def action_wait_to_exposed(self) -> OverviewRegisterState:
    # Move from wait to exposed position outside device
    resp = await self._send_cmd("mv", "wh", "")
    return OverviewRegisterState.from_resp(resp)

  async def action_exposed_to_wait(self) -> OverviewRegisterState:
    # Return to wait from exposed, close door
    resp = await self._send_cmd("mv", "hw", "")
    return OverviewRegisterState.from_resp(resp)

  async def action_exposed_to_storage(self, site: PlateHolder) -> OverviewRegisterState:
    # Return with MTP from exposed to storage, move to wait, close door
    resp = await self._send_cmd("mv", "hs", self._site_to_firmware_string(site))
    return OverviewRegisterState.from_resp(resp)

  async def action_storage_to_exposed(self, site: PlateHolder) -> OverviewRegisterState:
    # Move from wait to storage, load MTP, transport to exposed
    resp = await self._send_cmd("mv", "sh", self._site_to_firmware_string(site))
    return OverviewRegisterState.from_resp(resp)

  async def action_read_barcode(
    self,
    site_number_a: str,
    site_number_b: str,
  ) -> OverviewRegisterState:
    # Read barcode of storage locations
    validate_storage_location_number(site_number_a)
    validate_storage_location_number(site_number_b)
    resp = await self._send_cmd("mv", "sn", f"{site_number_a} {site_number_b}")
    return OverviewRegisterState.from_resp(resp)

  async def wait_for_transfer_station_to_be_unoccupied(self):
    while (await self.get_overview_register()).transfer_station_occupied:
      await asyncio.sleep(1)

  async def wait_for_transfer_station_to_be_occupied(self):
    while not (await self.get_overview_register()).transfer_station_occupied:
      await asyncio.sleep(1)

  async def wait_for_task_completion(self, timeout=60):
    # TODO #108 - turn this into a context that insulates both sides of an action
    start = time.time()
    while True:
      overview_register = await self.get_overview_register()
      if not overview_register.busy_bit_set:
        break
      await asyncio.sleep(1)
      if time.time() - start > timeout:
        raise TimeoutError("Cytomat did not complete task in time")

  async def init_shakers(self):
    return hex_to_binary(await self._send_cmd("ll", "vi", ""))

  async def start_shaking(self, frequency: float):
    await self.wait_for_task_completion()
    if self.model == CytomatType.C5C:
      raise NotImplementedError("Shaking is not supported on this model")

    # TODO: call set_shaking_frequency here

    return hex_to_binary(await self._send_cmd("ll", "va", ""))

  async def stop_shaking(self):
    await self.wait_for_task_completion()
    if self.model == CytomatType.C5C:
      raise NotImplementedError("Shaking is not supported on this model")

    return hex_to_binary(await self._send_cmd("ll", "vd", ""))

  async def set_shaking_frequency(self, frequency: int, shaker: Optional[int] = 0):
    if shaker == 1 or shaker == 0:
      hex1 = await self._send_cmd("se", "pb 20", f"{frequency:04}")
      if shaker == 1:
        return hex1
    if shaker == 2 or shaker == 0:
      hex2 = await self._send_cmd("se", "pb 21", f"{frequency:04}")
      if shaker == 2:
        return hex_to_binary(hex2)
    if shaker == 0:
      return hex_to_binary(hex1), hex_to_binary(hex2)
    raise ValueError("Shaker number must be 1, 2 or 0 for both")

  async def get_incubation_query(
    self, query: Literal["ic", "ih", "io", "it"]
  ) -> CytomatIncupationResponse:
    resp = await self._send_cmd("ch", query, "")
    nominal, actual = resp.split()
    return CytomatIncupationResponse(
      nominal_value=float(nominal.lstrip("+")), actual_value=float(actual.lstrip("+"))
    )

  async def get_co2(self) -> CytomatIncupationResponse:
    return await self.get_incubation_query("ic")

  async def get_humidity(self) -> CytomatIncupationResponse:
    return await self.get_incubation_query("ih")

  async def get_o2(self) -> CytomatIncupationResponse:
    return await self.get_incubation_query("io")

  async def get_temperature(self) -> float:
    return (await self.get_incubation_query("it")).actual_value

  async def fetch_plate_to_loading_tray(self, plate: Plate):
    site = plate.parent
    assert isinstance(site, PlateHolder)
    await self.action_storage_to_transfer(site)

  async def take_in_plate(self, plate: Plate, site: PlateHolder):
    await self.action_transfer_to_storage(site)

  async def set_temperature(self, *args, **kwargs):
    raise NotImplementedError("Temperature control is not implemented yet")


class CytomatChatterbox(Cytomat):
  async def setup(self):
    print("CytomatChatterbox setup")

  async def stop(self):
    print("CytomatChatterbox stop")

  async def _send_cmd(self, command_type, command, params, retries=3):
    print(self._assemble_command(command_type=command_type, command=command, params=params))
    if command_type == "ch":
      return "0"
    return "0" * 8
