from __future__ import print_function

def main(event, context):
	for i in range(10 ** 7):
		hash(i)

	print(event, context)
	return 11