from json import load
from struct import pack
from io import IOBase
from typing import Any
from os.path import join, getsize

JSON_FILE = "dump\\out\\out.wad.pc.json"
FILES = "dump\\out\\files"

WAD_ARCHIVE = "dump\\out\\out.wad.pc"

HEADER: bytes = bytes.fromhex("57414401")

class BinaryWriter():
	_file: IOBase
	_endian: str

	def __init__(self, file: IOBase) -> None:
		self._file = file
		self._endian = "@"

	def set_endian(self, endian: str) -> None:
		self._endian = endian

	def tell(self) -> int:
		return self._file.tell()

	def write(self, format: str, data: Any) -> int | None:
		self._file.write(pack(f"{self._endian}{format}", data))

	def write_uint8(self, data: int) -> int | None:
		return self.write("B", data)
		
	def write_int8(self, data: int) -> int | None:
		return self.write("b", data)
		
	def write_uint16(self, data: int) -> int | None:
		return self.write("H", data)
		
	def write_int16(self, data: int) -> int | None:
		return self.write("h", data)

	def write_uint32(self, data: int) -> int | None:
		return self.write("I", data)
		
	def write_int32(self, data: int) -> int | None:
		return self.write("i", data)
		
	def write_uint64(self, data: int) -> int | None:
		return self.write("Q", data)
		
	def write_int64(self, data: int) -> int | None:
		return self.write("q", data)

	def write_float32(self, data: float) -> int | None:
		return self.write("f", data)
		
	def write_float64(self, data: float) -> int | None:
		return self.write("d", data)

	def write_string(self, data: str) -> int | None:
		self.write(f"{len(data)}s", data.encode())

	def write_chunk(self, data: Any) -> int | None:
		return self._file.write(data)


with open(JSON_FILE, "r") as json_file:
	archive_data = load(json_file)

with open(WAD_ARCHIVE, "wb") as wad_file:
	writer = BinaryWriter(wad_file)
	
	writer.write_string("WAD\x01")
	writer.write_uint32(archive_data["num_files"])
	
	file_data = []
	offset = 8 + archive_data["num_files"] * 12

	for file_data in archive_data["files"]:
		path: str = join(FILES, file_data["name"])
		size: int = getsize(path)
		file_data["offset"] = offset
		file_data["size"] = size
		writer.write_uint32(file_data["hash"])
		writer.write_uint32(file_data["offset"])
		writer.write_uint32(file_data["size"])
		offset += size

	for file_data in archive_data["files"]:
		with open(join(FILES, file_data["name"]), "rb") as file:
			writer.write_chunk(file.read())

	for file_data in archive_data["files"]:
		name = file_data["name"]
		writer.write_uint16(len(name))
		writer.write_string(name)
