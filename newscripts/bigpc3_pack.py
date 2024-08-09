import io
import xml.etree.ElementTree as ET
import struct
import sys, os

import zlib

XML_DATA_FILE: str = "entries.xml"
ENDIANNESS: str = ""
DIRECTORY: str = ""

# XML FUNCTIONS

def get_tree_root(file_directory: str) -> ET.Element:
	tree = ET.parse(file_directory + XML_DATA_FILE)
	return tree.getroot()

def get_tree_table(root: ET.Element) -> ET.Element:
	return root.find("table") #type: ignore

def get_tree_segments(root: ET.Element) -> ET.Element:
	return root.find("segments") #type: ignore

# COMPRESSOR

def pack_with_zlib(data: bytes) -> tuple[bytes, int]:
	data = zlib.compress(data, level = 9, wbits = -15)
	data_size: int = len(data)
	return data, data_size

# DATA FUNCTIONS

def check_archive_type(table: ET.Element, segments: ET.Element) -> None:
	if (table.get("archive_type") != "3"):
		raise Exception("Unsupported archive")

	# if entries count in table is 0, but in segments is not 0
	if (table.get("num_entries") == "0" and len(segments.findall("segment"))):
		raise Exception("Case 0 not supported for now")
	return

def get_header_size(data: bytes, first_block_size: int) -> int: # for 2-blocked arhives
	try:
		magic: bytes = struct.unpack(ENDIANNESS + "4s", data[0:4])[0]

		if(magic != b"trM#"):
			raise Exception

		block1size, _block2size = struct.unpack(ENDIANNESS + "2I", data[8:16]) # is endianness static? 0x21-0x24 - pointer to Trm 

		return block1size
	except:
		return first_block_size

def data_to_chunk_pattern(data: bytes) -> tuple[bytes, int]:
	padding_size: int = 0x10 - (len(data) % 0x10)
	if padding_size != 0x10:
		data += b"\x00" * padding_size
	return data, padding_size % 0x10

def get_buffer_rounds(data_size: int) -> tuple[int, int]:
	comparison_value: int = 2**16 # buffer size? or just short value

	size_coefficient: int = data_size // comparison_value
	remainder_size: int = data_size % comparison_value

	return remainder_size, size_coefficient

def single_segment_handler(row: ET.Element, segment: ET.Element, file_to_write: io.BufferedWriter) -> dict[str, int]: # without chunks
	#raise Exception("todo")
	multiblocked_segment = False
	block1_size = 0
	if b1 := row.find("decompressed_block1_size"):
		block1_size = int(b1.text or "0")
	
	if (b2 := row.find("decompressed_block2_size")) and b2.text != "0":
		multiblocked_segment = True
		
	decompressed_main_block_size = 0
	data_to_write = b""
	with open(DIRECTORY + (row.get("hash") or ""), "rb") as file_to_read:
		if multiblocked_segment:
			block1_size = get_header_size(file_to_read.read(0x10), block1_size) # trM has size of blocks
			file_to_read.seek(0)

			print(f"{block1_size}")

			data_to_write += file_to_read.read(block1_size)
		
		decompressed_main_block_size = file_to_read.tell()
		data_to_write += file_to_read.read()
		decompressed_main_block_size = file_to_read.tell() - decompressed_main_block_size
		offset: int = decompressed_main_block_size % 16
		if offset:
			print(row.get("hash"), "is offset", offset)
			data_to_write += (b"X" * (16 - offset))
			decompressed_main_block_size += (16 - offset)
		# print(f"{decompressed_main_block_size}")

	current_offset_position = file_to_write.tell()
	file_to_write.write(data_to_write)

	table_row_dict = {
		"hash": int(row.get("hash") or "", 16),
		"offset": current_offset_position >> 4,
		"block1_size": block1_size if block1_size else decompressed_main_block_size, # block1 is static
		"block2_size": decompressed_main_block_size if block1_size else 0,
		"compressed_size": 0
	}

	return table_row_dict

# in row compressed size = full value of segment (include seg header + chunks headers + chunk data). size1-size2 = only decompressed data size
def multi_segment_handler(row: ET.Element, segment: ET.Element, file_to_write: io.BufferedWriter): # in main has many chunks
	multiblocked_segment = False 
	block1_size = None
	decompressed_main_block_size = 0

	flag_value = 0x10

	magic_value = "sges"    # 4 bytes
	segment_type = 7        # 2 bytes
	num_chunks = 0          # 2 bytes
	object_count = 0        # 4 bytes

	if segment.get("u0") != "0":
		raise Exception("Objects not supported for now")

	if row.find("decompressed_block2_size").text != "0":
		multiblocked_segment = True
		block1_size = int(row.find("decompressed_block1_size").text)
		
	data_to_write = b""
	with open(DIRECTORY + row.get("hash"), "rb") as file_to_read: # reads ONLY hash-named files
		file_to_read.seek(0, 2)  
		decompressed_file_size = file_to_read.tell()  # get decompressed file size
		file_to_read.seek(0)

		segment_info_list = list()

		while True: # chunk writer
			if (decompressed_file_size < 100): # TODO: find real uncompressed value
				local_decompressed_data = file_to_read.read()
				decompressed_data_size = len(local_decompressed_data)
				decompressed_main_block_size += decompressed_data_size

				chunk_data, zero_count = data_to_chunk_pattern(local_decompressed_data)
				data_to_write += chunk_data
				decompressed_data_size += zero_count

				decompressed_data_size, size_coefficient = get_buffer_rounds(decompressed_data_size) 

				parameters_dict = {
					"size": decompressed_data_size,
					"flags": 0x00,
					"size_coeff": size_coefficient
				}

				segment_info_list.append(parameters_dict)

				num_chunks += 1
				break

			if multiblocked_segment:
				multiblocked_segment = False
				flag_value = 0x11
				block_size = int(row.find("decompressed_block1_size").text)
				block_size = get_header_size(file_to_read.read(0x10), block_size) # trM has size of blocks
				file_to_read.seek(0)
				
				local_decompressed_data = file_to_read.read(block_size)
				decompressed_data_size = len(local_decompressed_data) # useless? 

				local_compressed_data, compressed_data_size = pack_with_deflate(local_decompressed_data) if deflate_available else pack_with_zlib(local_decompressed_data)
				chunk_data, zero_count = data_to_chunk_pattern(local_compressed_data)
				data_to_write += chunk_data
				compressed_data_size += zero_count 
				compressed_data_size, size_coefficient = get_buffer_rounds(compressed_data_size) 

				parameters_dict = {
					"size": compressed_data_size,
					"flags": 0x10,
					"size_coeff": size_coefficient
				}

				segment_info_list.append(parameters_dict)

			else:
				local_decompressed_data = file_to_read.read(2**17)
				decompressed_data_size = len(local_decompressed_data) 
				decompressed_main_block_size += decompressed_data_size 

				local_compressed_data, compressed_data_size = pack_with_deflate(local_decompressed_data) if deflate_available else pack_with_zlib(local_decompressed_data)
				chunk_data, zero_count = data_to_chunk_pattern(local_compressed_data)
				data_to_write += chunk_data
				compressed_data_size += zero_count 
				compressed_data_size, size_coefficient = get_buffer_rounds(compressed_data_size)

				parameters_dict = {
					"size": compressed_data_size,
					"flags": flag_value,
					"size_coeff": size_coefficient
				}

				segment_info_list.append(parameters_dict)

			num_chunks += 1

			if (not (file_to_read.tell() - decompressed_file_size)):
				break
				#remaining_part = file_to_read.read()

		segment_header = struct.pack(ENDIANNESS + "4sHHI", magic_value.encode(), segment_type, num_chunks, object_count)

		counter = 0
		for segment_data in segment_info_list:
			compressed_data_size, flag_value, size_coefficient = segment_data.values()
			segment_header += struct.pack(ENDIANNESS + "H2B", compressed_data_size, flag_value, size_coefficient)
			counter += 1

		segment_header, padding_val = data_to_chunk_pattern(segment_header)
		data_to_write = segment_header + data_to_write

		current_offset_position = file_to_write.tell()
		file_to_write.write(data_to_write)
		
		table_row_dict = {
			"hash": int(row.get("hash"), 16),
			"offset": current_offset_position >> 4,
			"block1_size": block1_size if block1_size else decompressed_main_block_size, # block1 is static
			"block2_size": decompressed_main_block_size if block1_size else 0,
			"compressed_size": len(data_to_write)
		}

	return table_row_dict

def big_packer(directory_path: str):
	global ENDIANNESS
	global DIRECTORY
	table_rows: list[dict[str, int]] = []

	if not directory_path.endswith("\\"):
		directory_path += "\\"

	DIRECTORY = directory_path #type: ignore

	root = get_tree_root(directory_path)
	ENDIANNESS = root.get("endianness") #type: ignore
	file_name: str = root.get("file_name") or ""

	row_table = get_tree_table(root)
	segment_table = get_tree_segments(root)

	check_archive_type(row_table, segment_table)

	with open(directory_path + file_name, "wb") as file:
		rows = row_table.findall("row")
		segments = segment_table.findall("segment")

		for row, segment in zip(rows, segments):
			case_num = segment.get("case")

			if (case_num == "1"):
				table_rows.append(single_segment_handler(row, segment, file))
			elif (case_num == "2"):
				table_rows.append(multi_segment_handler(row, segment, file))
			else:
				raise Exception("Unknown case")
			
		table_data: bytes = b""
		entries_count: int = 0

		for entries_data in table_rows:
			hash_value, offset_value, block1_size, block2_size, compressed_size = entries_data.values()
			table_data += struct.pack(ENDIANNESS + "5I", hash_value, offset_value, block1_size, block2_size, compressed_size)
			entries_count += 1

		table_data = struct.pack("<2I", 3, entries_count) + table_data # memory full? Endianness static?
		
		table_start_position = file.tell()
		file.write(table_data)

		table_offset = file.tell() + 4 - table_start_position # integer for offset
		file.write(struct.pack("<I", table_offset)) # write offset to the end
	return True

# START
folder_path: str = sys.argv[1:][0]

if not os.path.exists(folder_path):
	folder_path = input("Path to folder: ")

if not os.path.exists(folder_path):
	raise Exception("Path does not exist")

if (big_packer(f"{folder_path}")):
	print("Ready!")
