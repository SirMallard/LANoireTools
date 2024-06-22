from io import BufferedReader
from json import dump
import os
import argparse

def read_bytes(file: BufferedReader, address: int, size: int) -> bytes:
	file.seek(address)
	return file.read(size)

def find_signature(file: BufferedReader, signature: str) -> list[int]:
	data: bytes = file.read()
	signature_bytes: bytes = bytes.fromhex(signature)
	start: int = 0
	addresses: list[int] = []
	while start < len(data):
		pos: int = data.find(signature_bytes, start)
		if pos == -1:
			break
		#addresses.append(format(pos, "x"))
		addresses.append(pos)
		start = pos + 1
	return addresses

def find_signature_bytes(file: BufferedReader, signature_bytes: bytes) -> list[int]:
	data: bytes = file.read()
	start: int = 0
	addresses: list[int] = []
	while start < len(data):
		pos: int = data.find(signature_bytes, start)
		if pos == -1:
			break
		addresses.append(pos)
		start = pos + 1
	return addresses

def get_bin_element_size(file: BufferedReader, string_size_address: int, bytes_size: int) -> int:
	_: bytes = file.read()
	#string_size_address = signature_address + signature_size
	string_size_bytes: bytes = read_bytes(file, string_size_address, bytes_size)
	return int.from_bytes(string_size_bytes, byteorder='little')

def get_string_value(file: BufferedReader, string_value_address: int, string_size: int) -> str:
	_: bytes = file.read()
	#string_value_address = signature_address + signature_size + 1
	string_bytes: bytes = read_bytes(file, string_value_address, string_size)
	return string_bytes.decode('utf-8')

def get_table_string_count(file: BufferedReader, string_count_address: int) -> int:
	return get_bin_element_size(file, string_count_address, 2)

def get_table_strings(file: BufferedReader, string_table_address: int, string_count: int, lang_count: int) -> tuple[list[str], list[str]]:
	_: bytes = file.read()
	strings_id: list[str] = []
	strings_value: list[str] = []

	current_string: int = 0
	current_address: int = string_table_address

	while current_string < string_count:
		current_address += 9
		# print(f'{current_address}')
		
		string_id_size: int = get_bin_element_size(file, current_address, 2)
		current_address += 2
		string_id: str = get_string_value(file, current_address, string_id_size)
		# print(f'{current_string}: {string_id}')
		strings_id.append(string_id)
		current_address += string_id_size

		current_lang_string: int = 0

		while current_lang_string < lang_count:
			current_address += 5
			
			string_value_size: int = get_bin_element_size(file, current_address, 2)
			current_address += 2

			if string_value_size > 0:
				string_value: str = get_string_value(file, current_address, string_value_size)
				# print(f'{current_lang_string}: {string_value}')
				strings_value.append(string_value)
			else:
				strings_value.append("")

			current_address += string_value_size
			current_lang_string += 1

		current_address += 1
		current_string += 1
	
	return strings_id, strings_value

def write_to_file(full_path: str, string_value: str, set_formatted: int, start_value: str) -> None:
	# is file exist, if not - create
	if not os.path.exists(full_path):
		open(full_path, 'w').close()

	if set_formatted:
		string_value = f'{start_value}"{string_value}"'

	with open(full_path, 'a', encoding='utf-8') as file:
		file.write(string_value + '\n')

def clear_file(filename: str) -> None:
	if os.path.exists(filename):
		open(filename, 'w').close()

# --- code start ---
# Parser creation
parser = argparse.ArgumentParser(description='Unpack ATB files.')
# Argument list
parser.add_argument('filename', help='The name of the file to unpack.')
# parser.add_argument('directory', help='The directory of the files to unpack.')
parser.add_argument('--outputpath', default='', help='The path to save the output files.')
parser.add_argument('--setformatted', action='store_true', help='Format the output strings.')
parser.add_argument('--addenter', action='store_true', help='Add an additional enter to the output.')

# Arguments parsing
args = parser.parse_args()

filename = args.filename
outfilename = args.outputpath if args.outputpath else filename
set_formatted = 1 if args.setformatted else 0
additional_enter = 1 if args.addenter else 0

# filename = 'test.atb'
string_table_signature = '3E80671C'
string_table_signature_bytes = bytes.fromhex(string_table_signature)
signature_size = len(string_table_signature_bytes)
bytes_stringtable_size = 1
#string_count_size = 2

LANGUAGE_COUNT = 7
# 1 = English
# 2 = French
# 3 = German
# 4 = Italian
# 5 = Japanese
# 6 = Russian
# 7 = Spanish

set_formatted: int = 0 # true

# outfilename = filename
if '.atb' in outfilename:
	outfilename = outfilename.replace('.atb', '.txt')
else:
	outfilename += '.txt'

clear_file(outfilename)

data_table = {}

with open(filename, 'rb') as file:
	addresses = find_signature_bytes(file, string_table_signature_bytes)
	# print(f'Signature addresses: {addresses}')
	for address in addresses:
		size_offset = address + signature_size
		
		string_size = get_bin_element_size(file, size_offset, bytes_stringtable_size)
		string_value = get_string_value(file, size_offset + bytes_stringtable_size, string_size)
					
		write_to_file(outfilename, string_value, set_formatted, 't')

		substring_count_offset = size_offset + bytes_stringtable_size + string_size + 6
		substring_count = get_table_string_count(file, substring_count_offset)

		print(f'String table in \033[95m{address}\033[00m: (\033[95m{string_size}\033[00m) \033[95m{string_value}\033[00m have \033[95m{substring_count}\033[00m substrings')

		strings_id, strings_value = get_table_strings(file, substring_count_offset + 2, substring_count, LANGUAGE_COUNT)
		# print(f"Strings: \033[95m{strings_id}\033[00m")

		data_table[string_value] = {strings_id[i] : strings_value[LANGUAGE_COUNT * i : LANGUAGE_COUNT * (i + 1)] for i in range(len(strings_id))}

		# for i in range(len(strings_id)):
			
		# 	write_to_file(outfilename, strings_id[i], set_formatted, 'i')
		# 	substring_values = strings_value[i*7 : (i+1)*7]
		# 	print("ID:", strings_id[i], substring_values)
		# 	for substring in substring_values:
		# 		write_to_file(outfilename, substring, set_formatted, 's')

with open(f"{outfilename}.json", "w") as file:
	dump(data_table, file, indent = "\t")
